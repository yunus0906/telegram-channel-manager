from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio

import pytest
from sqlalchemy import func, select
from telethon.errors import FloodWaitError

from app.core.config import Settings
from app.db.models import Base, Channel, Message, SyncTask
from app.db.session import Database
from app.services.export_service import ExportService
from app.services.media_service import MediaService
from app.services.message_store import MessageStore
from app.services.settings_service import SettingsService
from app.services.tasks import TaskService
from app.websocket.hub import EventHub
from app.workers.runner import TaskRunner


def telegram_message(message_id: int):
    return SimpleNamespace(id=message_id, date=datetime.now(timezone.utc), edit_date=None, message=f"message {message_id}",
                           views=None, forwards=None, reply_to_msg_id=None, photo=None, video=None, document=None)


class FakeClient:
    def __init__(self, fail_once: bool = False):
        self.fail_once = fail_once
        self.calls = 0

    async def iter_messages(self, _entity, *, limit: int, offset_id: int):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise FloodWaitError(None, 1)
        for message_id in (4, 3, 2, 1):
            if not offset_id or message_id < offset_id:
                yield telegram_message(message_id)


class FakeTelegram:
    def __init__(self, client):
        self.client = client

    async def require_authorized(self):
        return self.client

    async def entity(self, _chat_id):
        return object()


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor,expected,fail_once", [(3, 2, False), (None, 4, True)])
async def test_history_resumes_from_cursor_and_obeys_flood_wait(tmp_path, cursor, expected, fail_once):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'runner.db').as_posix()}")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-1001, title="测试", access_type="private")
        session.add(channel)
        await session.flush()
        session.add(SyncTask(id="history-task", channel_id=channel.id, task_type="history", status="running",
                             cursor_message_id=cursor, processed_count=2 if cursor else 0, options={}))
        await session.commit()
    client = FakeClient(fail_once)
    telegram = FakeTelegram(client)
    app_settings = SettingsService(db.sessions)
    hub = EventHub()
    runner = TaskRunner(db.sessions, telegram, MessageStore(db.sessions), TaskService(db.sessions),
                        ExportService(settings, db.sessions, app_settings),
                        MediaService(settings, db.sessions, app_settings, telegram, hub), app_settings, hub)
    await runner._run_history("history-task")
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == expected
        task = await session.get(SyncTask, "history-task")
        assert task.cursor_message_id == 1
        assert task.processed_count == 4
    assert client.calls == (2 if fail_once else 1)
    await db.close()


@pytest.mark.asyncio
async def test_repeated_flood_wait_has_retry_limit(tmp_path, monkeypatch):
    async def no_wait(_seconds):
        return None
    monkeypatch.setattr(asyncio, "sleep", no_wait)
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'flood.db').as_posix()}")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-1001, title="测试", access_type="private")
        session.add(channel)
        await session.flush()
        session.add(SyncTask(id="flood-task", channel_id=channel.id, task_type="history", status="running", options={}))
        await session.commit()

    class FloodingClient:
        calls = 0
        async def iter_messages(self, _entity, *, limit: int, offset_id: int):
            self.calls += 1
            if self.calls > 7:
                raise RuntimeError("retry was unbounded")
            raise FloodWaitError(None, 1)
            yield  # pragma: no cover

    client = FloodingClient()
    telegram = FakeTelegram(client)
    app_settings = SettingsService(db.sessions)
    hub = EventHub()
    runner = TaskRunner(db.sessions, telegram, MessageStore(db.sessions), TaskService(db.sessions),
                        ExportService(settings, db.sessions, app_settings),
                        MediaService(settings, db.sessions, app_settings, telegram, hub), app_settings, hub)
    with pytest.raises(FloodWaitError):
        await runner._run_history("flood-task")
    assert client.calls == 6
    await db.close()
