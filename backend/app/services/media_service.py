import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.paths import within_root
from app.db.models import Channel, MediaFile, Message
from app.services.settings_service import SettingsService
from app.telegram.client import TelegramManager
from app.websocket.hub import EventHub


class MediaService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession], app_settings: SettingsService,
                 telegram: TelegramManager, hub: EventHub):
        self.settings = settings
        self.sessions = sessions
        self.app_settings = app_settings
        self.telegram = telegram
        self.hub = hub

    async def root(self) -> Path:
        values = (await self.app_settings.get()).values
        path = within_root(self.settings.data_root, values.media_save_directory)
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def set_status(self, channel_id: int, message_id: int, status: str) -> None:
        async with self.sessions() as session:
            media = await session.scalar(select(MediaFile).where(
                MediaFile.channel_id == channel_id, MediaFile.telegram_message_id == message_id
            ))
            if media is None:
                media = MediaFile(channel_id=channel_id, telegram_message_id=message_id, status=status)
                session.add(media)
            else:
                media.status = status
            await session.commit()

    async def download(self, channel: Channel, message_id: int) -> Path:
        values = (await self.app_settings.get()).values
        if not values.media_download_enabled:
            raise AppError(409, "media_disabled", "媒体下载已关闭")
        async with self.sessions() as session:
            local = await session.scalar(select(Message).where(Message.channel_id == channel.id, Message.telegram_message_id == message_id))
            if local is None or not local.media_type:
                raise AppError(404, "media_not_found", "本地消息没有可下载的附件")
        source = await self.telegram.get_message(channel.telegram_chat_id, message_id)
        if not getattr(source, "media", None):
            raise AppError(404, "media_not_found", "Telegram 附件已不可访问")
        file_info = getattr(source, "file", None)
        expected_size = getattr(file_info, "size", None)
        if expected_size and expected_size > self.settings.media_max_bytes:
            raise AppError(413, "media_too_large", "附件超过大小限制")
        root = await self.root()
        temp_dir = Path(tempfile.mkdtemp(prefix="download-", dir=root))
        last_notice = 0

        def progress(done: int, total: int) -> None:
            nonlocal last_notice
            if done > self.settings.media_max_bytes:
                raise AppError(413, "media_too_large", "附件超过大小限制")
            if done - last_notice >= 1024 * 1024 or done == total:
                last_notice = done
                asyncio.create_task(self.hub.publish({
                    "event_id": f"media-{channel.telegram_chat_id}-{message_id}-{done}", "type": "media.progress",
                    "channel_id": str(channel.telegram_chat_id), "message_id": str(message_id),
                    "timestamp": None, "data": {"processed_count": done, "total_count": total},
                }))

        try:
            client = await self.telegram.require_authorized()
            saved = await asyncio.wait_for(client.download_media(source, file=str(temp_dir), progress_callback=progress), timeout=600)
            if not saved:
                raise AppError(502, "media_download_failed", "Telegram 未返回附件文件")
            downloaded = Path(saved).resolve()
            if not downloaded.is_relative_to(temp_dir.resolve()) or not downloaded.is_file():
                raise AppError(502, "media_download_failed", "附件保存位置无效")
            size = downloaded.stat().st_size
            if size > self.settings.media_max_bytes:
                raise AppError(413, "media_too_large", "附件超过大小限制")
            suffix = downloaded.suffix.lower()[:12]
            if not suffix or not suffix[1:].isalnum():
                suffix = ".bin"
            relative = f"{root.relative_to(self.settings.data_root).as_posix()}/{channel.telegram_chat_id}/{message_id}{suffix}"
            target = within_root(self.settings.data_root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            checksum = await asyncio.to_thread(self._checksum, downloaded)
            os.replace(downloaded, target)
            async with self.sessions() as session:
                async with session.begin():
                    media = await session.scalar(select(MediaFile).where(
                        MediaFile.channel_id == channel.id, MediaFile.telegram_message_id == message_id
                    ))
                    if media is None:
                        media = MediaFile(channel_id=channel.id, telegram_message_id=message_id)
                        session.add(media)
                    media.original_filename = getattr(file_info, "name", None)
                    media.relative_path = relative
                    media.mime_type = getattr(file_info, "mime_type", None)
                    media.size_bytes = size
                    media.status = "completed"
                    media.checksum = checksum
                    local = await session.scalar(select(Message).where(Message.channel_id == channel.id, Message.telegram_message_id == message_id))
                    if local:
                        local.media_path = relative
            return target
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    async def path(self, channel_id: int, message_id: int) -> Path:
        async with self.sessions() as session:
            media = await session.scalar(select(MediaFile).where(
                MediaFile.channel_id == channel_id, MediaFile.telegram_message_id == message_id,
                MediaFile.status == "completed"
            ))
            if media is None or not media.relative_path:
                raise AppError(404, "media_not_downloaded", "附件尚未下载")
            path = within_root(self.settings.data_root, media.relative_path)
            if not path.is_file():
                raise AppError(404, "media_missing", "本地附件文件不存在")
            return path

