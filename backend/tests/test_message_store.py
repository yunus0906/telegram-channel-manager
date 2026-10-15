from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import Base, Channel, Message, SyncEvent, SyncTask
from app.db.session import Database
from app.services.message_store import MessageStore


@pytest.mark.asyncio
async def test_repeated_message_updates_without_duplicate_event(tmp_path):
    db = Database(Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"))
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-100123, title="测试", access_type="private")
        session.add(channel)
        await session.commit()
        channel_id = channel.id
    store = MessageStore(db.sessions)
    msg = SimpleNamespace(id=7, date=datetime.now(timezone.utc), edit_date=None, message="原文", views=1,
                          forwards=None, reply_to_msg_id=None, photo=None, video=None, document=None)
    assert len(await store.save_batch(channel_id, [msg])) == 1
    msg.views = 2
    assert await store.save_batch(channel_id, [msg]) == []
    msg.message = "修改"
    events = await store.save_batch(channel_id, [msg])
    assert [item["type"] for item in events] == ["message.edited"]
    async with db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == 1
        assert await session.scalar(select(func.count()).select_from(SyncEvent)) == 2
    await db.close()


@pytest.mark.asyncio
async def test_cursor_commits_with_messages(tmp_path):
    db = Database(Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"))
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-100123, title="测试", access_type="private")
        task = SyncTask(id="task-1", channel_id=1, task_type="history", status="running")
        session.add(channel)
        await session.flush()
        task.channel_id = channel.id
        session.add(task)
        await session.commit()
        channel_id = channel.id
    msg = SimpleNamespace(id=7, date=datetime.now(timezone.utc), edit_date=None, message="原文", views=None,
                          forwards=None, reply_to_msg_id=None, photo=None, video=None, document=None)
    await MessageStore(db.sessions).save_batch(channel_id, [msg], task_id="task-1", cursor=7)
    async with db.sessions() as session:
        task = await session.get(SyncTask, "task-1")
        assert task.cursor_message_id == 7
        assert task.processed_count == 1
    await db.close()
