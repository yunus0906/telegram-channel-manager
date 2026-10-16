import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Channel, Message, SyncEvent, SyncTask, utcnow, as_utc


BUSINESS_FIELDS = ("text", "edit_date", "media_type", "reply_to_message_id")


def message_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return any((as_utc(old.get(field)) != as_utc(new.get(field)) if field == "edit_date"
                else old.get(field) != new.get(field)) for field in BUSINESS_FIELDS)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def media_kind(message: Any) -> str | None:
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "media", None):
        return "other"
    return None


class MessageStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions
        self._locks: dict[int, asyncio.Lock] = {}

    async def save_batch(
        self, channel_id: int, messages: Sequence[Any], *, task_id: str | None = None, cursor: int | None = None
    ) -> list[dict[str, Any]]:
        if not messages:
            return []
        lock = self._locks.setdefault(channel_id, asyncio.Lock())
        emitted: list[dict[str, Any]] = []
        async with lock:
            async with self.sessions() as session:
                async with session.begin():
                    channel = await session.get(Channel, channel_id)
                    if channel is None:
                        raise ValueError("频道不存在")
                    for source in messages:
                        telegram_id = int(source.id)
                        row = await session.scalar(select(Message).where(
                            Message.channel_id == channel_id, Message.telegram_message_id == telegram_id
                        ))
                        data = {
                            "text": source.message or "",
                            "edit_date": as_utc(source.edit_date),
                            "media_type": media_kind(source),
                            "reply_to_message_id": getattr(source, "reply_to_msg_id", None),
                            "views": getattr(source, "views", None),
                            "forwards": getattr(source, "forwards", None),
                        }
                        change: str | None = None
                        if row is None:
                            row = Message(
                                channel_id=channel_id,
                                telegram_message_id=telegram_id,
                                message_date=as_utc(source.date),
                                permalink=f"https://t.me/{channel.username}/{telegram_id}" if channel.username else None,
                                raw_metadata={},
                                **data,
                            )
                            session.add(row)
                            change = "message.new"
                        else:
                            old = {field: getattr(row, field) for field in BUSINESS_FIELDS}
                            if message_changed(old, data):
                                change = "message.edited"
                            for key, value in data.items():
                                setattr(row, key, value)
                            row.message_date = as_utc(source.date)
                            row.permalink = f"https://t.me/{channel.username}/{telegram_id}" if channel.username else None
                        if channel.last_message_id is None or telegram_id > channel.last_message_id:
                            channel.last_message_id = telegram_id
                        if change:
                            event = SyncEvent(
                                channel_id=channel_id,
                                telegram_message_id=telegram_id,
                                event_type=change,
                                payload={"text": data["text"], "edit_date": iso(data["edit_date"]), "media_type": data["media_type"]},
                            )
                            session.add(event)
                            await session.flush()
                            emitted.append({
                                "event_id": str(event.id), "type": change,
                                "channel_id": str(channel.telegram_chat_id), "message_id": str(telegram_id),
                                "timestamp": iso(event.created_at or utcnow()), "data": {},
                            })
                    if task_id:
                        task = await session.get(SyncTask, task_id)
                        if task is None:
                            raise ValueError("任务不存在")
                        task.cursor_message_id = cursor
                        task.processed_count += len(messages)
                        task.updated_at = utcnow()
        return emitted
