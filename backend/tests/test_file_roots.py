from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.db.models import Base, Channel, MediaFile, Message, SyncTask
from app.db.session import Database
from app.services.export_service import ExportService
from app.services.media_service import MediaService
from app.services.settings_service import SettingsService
from app.schemas.api import AppSettingsSchema
from app.websocket.hub import EventHub


@pytest.mark.asyncio
async def test_saved_files_remain_accessible_after_directory_setting_changes(tmp_path):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'files.db').as_posix()}")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    media_path = tmp_path / "old-media" / "-1001" / "5.bin"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"file")
    export_path = tmp_path / "old-exports" / "export-test.json"
    export_path.parent.mkdir(parents=True)
    export_path.write_text("{}", encoding="utf-8")
    async with db.sessions() as session:
        channel = Channel(telegram_chat_id=-1001, title="测试", access_type="private")
        session.add(channel)
        await session.flush()
        session.add(Message(channel_id=channel.id, telegram_message_id=5, message_date=datetime.now(timezone.utc), text="", raw_metadata={}, media_type="document"))
        session.add(MediaFile(channel_id=channel.id, telegram_message_id=5, relative_path="old-media/-1001/5.bin", status="completed"))
        session.add(SyncTask(id="export-test", channel_id=channel.id, task_type="json_export", status="completed", options={}, result_path="old-exports/export-test.json"))
        await session.commit()
    config = SettingsService(db.sessions)
    await config.put(AppSettingsSchema(media_save_directory="new-media", export_directory="new-exports"))
    media = MediaService(settings, db.sessions, config, None, EventHub())
    exports = ExportService(settings, db.sessions, config)
    assert await media.path(channel.id, 5) == media_path
    async with db.sessions() as session:
        task = await session.get(SyncTask, "export-test")
        assert await exports.download_path(task) == export_path
    await db.close()
