import asyncio
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.paths import within_root
from app.db.models import Channel, MediaFile, Message, SyncEvent, SyncTask, as_utc, utcnow
from app.services.message_store import iso
from app.services.settings_service import SettingsService


class ExportService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession], app_settings: SettingsService):
        self.settings = settings
        self.sessions = sessions
        self.app_settings = app_settings

    async def root(self) -> Path:
        values = (await self.app_settings.get()).values
        root = within_root(self.settings.data_root, values.export_directory)
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def media_root(self) -> Path:
        values = (await self.app_settings.get()).values
        return within_root(self.settings.data_root, values.media_save_directory)

    async def generate(self, task: SyncTask) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9-]+", task.id):
            raise AppError(422, "invalid_task_id", "任务 ID 无效")
        root = await self.root()
        suffix = {"json_export": ".json", "jsonl_export": ".jsonl", "zip_export": ".zip"}[task.task_type]
        target = root / f"{task.id}{suffix}"
        if task.task_type == "json_export":
            await self._write_json(target, task.channel_id, task.options)
        elif task.task_type == "jsonl_export":
            await self._write_jsonl(target, task.channel_id, task.options)
        else:
            await self._write_zip(target, task)
        return target

    async def _channel_rows(self, session: AsyncSession, channel_id: int | None) -> list[Channel]:
        stmt = select(Channel).where(Channel.is_managed.is_(True))
        if channel_id is not None:
            stmt = stmt.where(Channel.id == channel_id)
        return list((await session.scalars(stmt.order_by(Channel.id))).all())

    @staticmethod
    def _channel_dict(channel: Channel) -> dict[str, Any]:
        return {"id": str(channel.telegram_chat_id), "title": channel.title, "username": channel.username, "access_type": channel.access_type}

    @staticmethod
    def _message_dict(row: Message) -> dict[str, Any]:
        return {
            "message_id": str(row.telegram_message_id), "date": iso(row.message_date), "edit_date": iso(row.edit_date),
            "text": row.text, "views": row.views, "forwards": row.forwards,
            "reply_to_message_id": str(row.reply_to_message_id) if row.reply_to_message_id is not None else None,
            "media_type": row.media_type, "media_path": row.media_path, "permalink": row.permalink,
        }

    @staticmethod
    def _date_stmt(stmt, options: dict[str, Any], field):
        if options.get("date_from"):
            stmt = stmt.where(field >= as_utc(datetime.fromisoformat(options["date_from"])))
        if options.get("date_to"):
            stmt = stmt.where(field <= as_utc(datetime.fromisoformat(options["date_to"])))
        return stmt

    async def _write_json(self, target: Path, channel_id: int | None, options: dict[str, Any]) -> None:
        fd, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                async with self.sessions() as session:
                    channels = await self._channel_rows(session, channel_id)
                    if channel_id is not None and not channels:
                        raise AppError(404, "channel_not_found", "频道不存在")
                    exported_at = iso(utcnow())
                    if channel_id is None:
                        handle.write(json.dumps({"schema_version": 1, "exported_at": exported_at}, ensure_ascii=False)[:-1] + ',"channels":[')
                    else:
                        handle.write(json.dumps({"schema_version": 1, "channel": self._channel_dict(channels[0]), "exported_at": exported_at}, ensure_ascii=False)[:-1] + ',"messages":[')
                    for channel_index, channel in enumerate(channels):
                        if channel_id is None:
                            if channel_index:
                                handle.write(",")
                            handle.write(json.dumps({"channel": self._channel_dict(channel)}, ensure_ascii=False)[:-1] + ',"messages":[')
                        stmt = select(Message).where(Message.channel_id == channel.id).order_by(Message.message_date, Message.telegram_message_id)
                        stmt = self._date_stmt(stmt, options, Message.message_date)
                        first = True
                        result = await session.stream_scalars(stmt)
                        async for row in result:
                            if not first:
                                handle.write(",")
                            handle.write(json.dumps(self._message_dict(row), ensure_ascii=False))
                            first = False
                            if row.telegram_message_id % 100 == 0:
                                await asyncio.sleep(0)
                        if channel_id is None:
                            handle.write("]}")
                    handle.write("]}")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    async def _write_jsonl(self, target: Path, channel_id: int | None, options: dict[str, Any]) -> None:
        fd, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                async with self.sessions() as session:
                    stmt = select(SyncEvent, Channel.telegram_chat_id).join(Channel, Channel.id == SyncEvent.channel_id)
                    if channel_id is not None:
                        stmt = stmt.where(SyncEvent.channel_id == channel_id)
                    stmt = self._date_stmt(stmt, options, SyncEvent.created_at).order_by(SyncEvent.id)
                    result = await session.stream(stmt)
                    async for event, chat_id in result:
                        handle.write(json.dumps(self._event_dict(event, chat_id), ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _event_dict(event: SyncEvent, chat_id: int) -> dict[str, Any]:
        return {"schema_version": 1, "event_id": str(event.id), "type": event.event_type,
                "channel_id": str(chat_id), "message_id": str(event.telegram_message_id),
                "timestamp": iso(event.created_at), "data": event.payload}

    async def _write_zip(self, target: Path, task: SyncTask) -> None:
        json_path = target.with_suffix(".json")
        if not task.options.get("media_only"):
            await self._write_json(json_path, task.channel_id, task.options)
        fd, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        os.close(fd)
        try:
            with zipfile.ZipFile(temp_name, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                if not task.options.get("media_only"):
                    archive.write(json_path, "messages.json")
                if task.options.get("include_media"):
                    async with self.sessions() as session:
                        stmt = select(MediaFile, Channel.telegram_chat_id).join(Channel, Channel.id == MediaFile.channel_id).where(MediaFile.status == "completed")
                        if task.channel_id is not None:
                            stmt = stmt.where(MediaFile.channel_id == task.channel_id)
                        result = await session.stream(stmt)
                        async for media, chat_id in result:
                            if not media.relative_path:
                                continue
                            source = within_root(self.settings.data_root, media.relative_path)
                            if source.is_file():
                                suffix = source.suffix.lower()[:12]
                                archive.write(source, f"media/{chat_id}/{media.telegram_message_id}{suffix}")
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    async def flush_events(self) -> None:
        root = await self.root()
        async with self.sessions() as session:
            rows = (await session.execute(
                select(SyncEvent, Channel.telegram_chat_id).join(Channel, Channel.id == SyncEvent.channel_id)
                .where(SyncEvent.exported_at.is_(None)).order_by(SyncEvent.id).limit(500)
            )).all()
            grouped: dict[int, list[SyncEvent]] = {}
            for event, chat_id in rows:
                grouped.setdefault(chat_id, []).append(event)
            for chat_id, events in grouped.items():
                path = root / f"events-{chat_id}.jsonl"
                with path.open("a", encoding="utf-8") as handle:
                    for event in events:
                        handle.write(json.dumps(self._event_dict(event, chat_id), ensure_ascii=False) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            for event, _ in rows:
                event.exported_at = utcnow()
            await session.commit()

    async def download_path(self, task: SyncTask) -> Path:
        if task.status != "completed" or not task.result_path:
            raise AppError(409, "export_not_ready", "导出文件尚未生成")
        path = within_root(self.settings.data_root, task.result_path)
        if not path.is_file():
            raise AppError(404, "export_missing", "导出文件不存在")
        return path
