import pytest
from pydantic import ValidationError
from telethon import TelegramClient

from app.core.config import Settings
from app.core.errors import AppError
from app.telegram.client import TelegramManager


class FakeClient:
    def __init__(self):
        self.connected = True

    def is_connected(self):
        return self.connected

    async def is_user_authorized(self):
        return True

    async def disconnect(self):
        self.connected = False

    async def connect(self):
        self.connected = True


@pytest.mark.asyncio
async def test_manual_disconnect_does_not_silently_reconnect(tmp_path):
    manager = TelegramManager(Settings(data_root=tmp_path, tg_api_id=1, tg_api_hash="test"))
    manager.client = FakeClient()
    await manager.disconnect()
    with pytest.raises(AppError):
        await manager.require_authorized()
    await manager.reconnect()
    assert (await manager.status()).authorized


@pytest.mark.asyncio
async def test_telegram_client_uses_configured_http_proxy(tmp_path, monkeypatch):
    async def connect_without_network(self):
        return None

    monkeypatch.setattr(TelegramClient, "connect", connect_without_network)
    manager = TelegramManager(Settings(_env_file=None, data_root=tmp_path, tg_api_id=1,
                                       tg_api_hash="test", tg_proxy_url="http://127.0.0.1:10809"))

    await manager.connect()

    assert manager.client is not None
    assert manager.client._proxy == ("http", "127.0.0.1", 10809)


@pytest.mark.parametrize("proxy_url", ["http:127.0.0.1:10809", "https://127.0.0.1:10809",
                                       "http://127.0.0.1", "http://127.0.0.1:10809/path"])
def test_invalid_telegram_proxy_url_is_rejected(proxy_url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tg_proxy_url=proxy_url)
