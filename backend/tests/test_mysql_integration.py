"""Opt-in integration check against an isolated MySQL 8 test database."""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.core.auth import AuthService
from app.core.config import Settings
from app.db.models import Channel, Message, SyncEvent, SyncTask, as_utc
from app.db.session import Database
from app.services.export_service import ExportService
from app.services.message_store import MessageStore
from app.services.settings_service import SettingsService


@pytest.mark.asyncio
async def test_mysql_migration_sync_auth_utc_and_export(tmp_path):
    configured_url = os.getenv("TCM_TEST_MYSQL_URL")
    if not configured_url:
        pytest.skip("TCM_TEST_MYSQL_URL is not configured")
    url = make_url(configured_url)
    if url.drivername != "mysql+aiomysql" or not url.database or not (url.database == "tcm_test" or url.database.startswith("tcm_test_")):
        pytest.fail("TCM_TEST_MYSQL_URL must point to a dedicated mysql+aiomysql tcm_test* database")
    settings = Settings(
        _env_file=None, data_root=tmp_path, db_type="mysql", mysql_host=url.host,
        mysql_port=url.port or 3306, mysql_user=url.username, mysql_password=url.password,
        mysql_database=url.database, admin_password_hash=PasswordHasher().hash("test-password"),
        session_secret="mysql-integration-test-secret",
    )
    db = Database(settings)
    try:
        await asyncio.to_thread(db.migrate)
        await asyncio.to_thread(db.migrate)
        async with db.engine.connect() as connection:
            assert (await connection.execute(text("SELECT @@session.time_zone"))).scalar() == "+00:00"
            assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar() == "0001_initial"

        chat_id = -100_000_000_000 - (uuid4().int % 1_000_000_000)
        task_id = str(uuid4())
        async with db.sessions() as session:
            channel = Channel(telegram_chat_id=chat_id, title="MySQL 验证", access_type="private")
            session.add(channel)
            await session.flush()
            channel_id = channel.id
            session.add(SyncTask(id=task_id, channel_id=channel_id, task_type="history", status="running", options={}))
            await session.commit()

        offset = timezone(timedelta(hours=8))
        source = SimpleNamespace(id=7, date=datetime(2026, 1, 1, 8, 30, tzinfo=offset),
                                 edit_date=datetime(2026, 1, 1, 8, 45, tzinfo=offset), message="测试消息",
                                 views=None, forwards=None, reply_to_msg_id=None, photo=None, video=None, document=None)
        store = MessageStore(db.sessions)
        assert len(await store.save_batch(channel_id, [source], task_id=task_id, cursor=7)) == 1
        assert await store.save_batch(channel_id, [source], task_id=task_id, cursor=7) == []
        async with db.sessions() as session:
            task = await session.get(SyncTask, task_id)
            row = await session.scalar(select(Message).where(Message.channel_id == channel_id))
            assert task.cursor_message_id == 7 and task.processed_count == 2
            assert as_utc(row.message_date) == datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
            assert as_utc(row.edit_date) == datetime(2026, 1, 1, 0, 45, tzinfo=timezone.utc)
            assert await session.scalar(select(func.count()).select_from(SyncEvent).where(SyncEvent.channel_id == channel_id)) == 1

        auth = AuthService(settings, db.sessions)
        token = await auth.login("test-password")
        assert token and await auth.valid(token)
        await auth.logout(token)
        assert not await auth.valid(token)

        export_task = SyncTask(id=str(uuid4()), channel_id=channel_id, task_type="json_export", status="running",
                               options={"date_from": "2026-01-01T08:00:00+08:00", "date_to": "2026-01-01T09:00:00+08:00"})
        path = await ExportService(settings, db.sessions, SettingsService(db.sessions)).generate(export_task)
        assert [item["message_id"] for item in json.loads(path.read_text(encoding="utf-8"))["messages"]] == ["7"]
    finally:
        await db.close()
