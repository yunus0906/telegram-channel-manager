import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.db.models import Channel, MediaFile, Message, SyncTask
from datetime import datetime, timezone
from app.main import create_app
from app.schemas.api import AppSettingsSchema


@pytest.mark.asyncio
async def test_admin_auth_and_offline_private_channel_listing(tmp_path):
    settings = Settings(
        data_root=tmp_path,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}",
        admin_password_hash=PasswordHasher().hash("admin password"),
        session_secret="long-random-test-session-secret",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions() as session:
            session.add(Channel(telegram_chat_id=-100123, title="私有频道", access_type="private", is_managed=True))
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/health")).status_code == 200
            assert (await client.get("/api/v1/channels")).status_code == 401
            login = await client.post("/api/v1/auth/login", json={"password": "admin password"})
            assert login.status_code == 200
            csrf = login.json()["csrf_token"]
            listed = await client.get("/api/v1/channels")
            assert listed.status_code == 200
            assert listed.json()["items"][0]["telegram_chat_id"] == "-100123"
            assert listed.json()["items"][0]["permalink"] is None
            assert listed.json()["items"][0]["created_at"].endswith(("Z", "+00:00"))
            assert (await client.put("/api/v1/settings", json={}, headers={"X-CSRF-Token": "wrong"})).status_code == 403
            assert (await client.put("/api/v1/settings", json={}, headers={"X-CSRF-Token": csrf})).status_code == 200


@pytest.mark.asyncio
async def test_purge_removes_saved_media_and_prior_export_files(tmp_path):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'purge.db').as_posix()}",
                        admin_password_hash=PasswordHasher().hash("admin password"), session_secret="long-random-test-session-secret")
    app = create_app(settings)
    media_path = tmp_path / "old-media" / "-100123" / "1.bin"
    export_path = tmp_path / "old-exports" / "old.json"
    media_path.parent.mkdir(parents=True)
    export_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"media")
    export_path.write_text("{}", encoding="utf-8")
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions() as session:
            channel = Channel(telegram_chat_id=-100123, title="私有频道", access_type="private", is_managed=True)
            session.add(channel)
            await session.flush()
            session.add(MediaFile(channel_id=channel.id, telegram_message_id=1, status="completed", relative_path="old-media/-100123/1.bin"))
            session.add(SyncTask(id="old-export", channel_id=channel.id, task_type="json_export", status="completed", options={}, result_path="old-exports/old.json"))
            await session.commit()
        await app.state.app_settings.put(AppSettingsSchema(media_save_directory="new-media", export_directory="new-exports"))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            csrf = (await client.post("/api/v1/auth/login", json={"password": "admin password"})).json()["csrf_token"]
            result = await client.post("/api/v1/channels/-100123/purge", json={"confirm_telegram_chat_id": "-100123"}, headers={"X-CSRF-Token": csrf})
            assert result.status_code == 200
            assert not media_path.exists()
            assert not export_path.exists()


@pytest.mark.asyncio
async def test_message_list_reports_media_failure_state(tmp_path):
    settings = Settings(data_root=tmp_path, database_url=f"sqlite+aiosqlite:///{(tmp_path / 'media.db').as_posix()}",
                        admin_password_hash=PasswordHasher().hash("admin password"), session_secret="long-random-test-session-secret")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions() as session:
            channel = Channel(telegram_chat_id=-100123, title="私有频道", access_type="private", is_managed=True)
            session.add(channel)
            await session.flush()
            session.add(Message(channel_id=channel.id, telegram_message_id=1, message_date=datetime.now(timezone.utc), text="", media_type="document", raw_metadata={}))
            session.add(MediaFile(channel_id=channel.id, telegram_message_id=1, status="failed"))
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/login", json={"password": "admin password"})
            response = await client.get("/api/v1/channels/-100123/messages")
            assert response.json()["items"][0]["media_status"] == "failed"
