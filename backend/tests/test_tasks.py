import pytest

from app.core.config import Settings
from app.db.models import Base, Channel, SyncTask
from app.db.session import Database
from app.services.tasks import TaskService
from app.core.errors import AppError


@pytest.mark.asyncio
async def test_duplicate_active_sync_returns_same_task_and_restart_resumes(tmp_path):
    db = Database(Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'tasks.db').as_posix()}"))
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-1001, title="测试", access_type="private")
        session.add(channel)
        await session.commit()
        channel_id = channel.id
    service = TaskService(db.sessions)
    first, created = await service.create("history", channel_id)
    second, created_again = await service.create("history", channel_id)
    assert created and not created_again and first.id == second.id
    async with db.sessions() as session:
        row = await session.get(SyncTask, first.id)
        row.status = "running"
        row.cursor_message_id = 40
        await session.commit()
    await service.recover_running()
    async with db.sessions() as session:
        row = await session.get(SyncTask, first.id)
        assert row.status == "pending" and row.cursor_message_id == 40
    await db.close()


@pytest.mark.asyncio
async def test_running_export_cannot_claim_to_pause(tmp_path):
    db = Database(Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'tasks.db').as_posix()}"))
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        session.add(SyncTask(id="export-1", task_type="json_export", status="running", options={}))
        await session.commit()
    with pytest.raises(AppError):
        await TaskService(db.sessions).action("export-1", "pause")
    await db.close()
