import json
import zipfile
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.db.models import Base, Channel, MediaFile, Message, SyncEvent, SyncTask
from app.db.session import Database
from app.services.export_service import ExportService
from app.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_snapshot_and_jsonl_are_parseable_and_zip_paths_are_safe(tmp_path):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'export.db').as_posix()}")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-100123, title="私有", access_type="private")
        session.add(channel)
        await session.flush()
        session.add(Message(channel_id=channel.id, telegram_message_id=4, message_date=datetime.now(timezone.utc), text="正文", raw_metadata={}))
        session.add(SyncEvent(channel_id=channel.id, telegram_message_id=4, event_type="message.new", payload={"text": "正文"}))
        task = SyncTask(id="export-json", channel_id=channel.id, task_type="json_export", status="running", options={})
        session.add(task)
        await session.commit()
    service = ExportService(settings, db.sessions, SettingsService(db.sessions))
    json_path = await service.generate(task)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["channel"]["id"] == "-100123"
    assert data["messages"][0]["message_id"] == "4"
    task.task_type = "jsonl_export"
    jsonl_path = await service.generate(task)
    assert json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])["event_id"] == "1"
    task.task_type = "zip_export"
    zip_path = await service.generate(task)
    with zipfile.ZipFile(zip_path) as archive:
        assert all(".." not in name and not name.startswith("/") for name in archive.namelist())
        assert archive.testzip() is None
    await db.close()


@pytest.mark.asyncio
async def test_media_only_zip_contains_downloaded_media_without_json(tmp_path):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'mediazip.db').as_posix()}")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    media_path = tmp_path / "media" / "-100123" / "4.bin"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"attachment")
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-100123, title="私有", access_type="private")
        session.add(channel)
        await session.flush()
        session.add(MediaFile(channel_id=channel.id, telegram_message_id=4, status="completed", relative_path="media/-100123/4.bin"))
        task = SyncTask(id="media-only", channel_id=channel.id, task_type="zip_export", status="running",
                        options={"include_media": True, "media_only": True})
        session.add(task)
        await session.commit()
    path = await ExportService(settings, db.sessions, SettingsService(db.sessions)).generate(task)
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == ["media/-100123/4.bin"]
    await db.close()


@pytest.mark.asyncio
async def test_export_date_filter_normalizes_offset_to_utc(tmp_path):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'dates.db').as_posix()}")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-100123, title="私有", access_type="private")
        session.add(channel)
        await session.flush()
        session.add(Message(channel_id=channel.id, telegram_message_id=4,
                            message_date=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc), text="in range", raw_metadata={}))
        task = SyncTask(id="dated-export", channel_id=channel.id, task_type="json_export", status="running",
                        options={"date_from": "2026-01-01T08:00:00+08:00", "date_to": "2026-01-01T09:00:00+08:00"})
        session.add(task)
        await session.commit()
    path = await ExportService(settings, db.sessions, SettingsService(db.sessions)).generate(task)
    assert [item["message_id"] for item in json.loads(path.read_text(encoding="utf-8"))["messages"]] == ["4"]
    await db.close()
