import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from telethon import TelegramClient
from telethon.errors import ApiIdInvalidError, AuthKeyUnregisteredError, FloodWaitError, PhoneNumberInvalidError

from app.core.config import Settings
from app.core.errors import AppError
from app.telegram import client as client_module
from app.telegram.client import TelegramManager, account_key, explain_error


class FakeTelegramClient:
    """替身客户端：只实现 TelegramManager 实际用到的接口。"""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.connected = True
        self.authorized = False
        self.me = None
        self.error: Exception | None = None
        self.code_requests: list[str] = []
        self.signed_in: list[dict] = []
        self.disconnects = 0

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False
        self.disconnects += 1

    def add_event_handler(self, *_args, **_kwargs):
        return None

    async def is_user_authorized(self):
        return self.authorized

    async def send_code_request(self, phone):
        self.code_requests.append(phone)
        if self.error is not None:
            raise self.error
        return object()

    async def sign_in(self, **kwargs):
        self.signed_in.append(kwargs)
        self.authorized = True
        return self.me

    async def get_me(self):
        return self.me


def install_fake_client(monkeypatch, *, error=None, authorized=False, me=None):
    created: list[FakeTelegramClient] = []

    def factory(*args, **kwargs):
        client = FakeTelegramClient(*args, **kwargs)
        client.error = error
        client.authorized = authorized
        client.me = me
        created.append(client)
        return client

    monkeypatch.setattr(client_module, "TelegramClient", factory)
    return created


def build_settings(tmp_path, **overrides) -> Settings:
    return Settings(_env_file=None, data_root=tmp_path, tg_api_id=1, tg_api_hash="test", **overrides)


def legacy_session(tmp_path) -> None:
    (tmp_path / "telegram.session").touch()


def account_session(tmp_path, digits: str) -> None:
    directory = tmp_path / "accounts" / digits
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "telegram.session").touch()


def read_index(tmp_path) -> dict:
    return json.loads((tmp_path / "accounts" / "index.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------- 手机号与错误提示


def test_account_key_requires_explicit_country_code():
    assert account_key("+86 138 0000 0000") == "8613800000000"
    with pytest.raises(AppError) as missing:
        account_key("13800000000")
    assert missing.value.code == "phone_country_code_required"
    with pytest.raises(AppError) as malformed:
        account_key("+86abc")
    assert malformed.value.code == "phone_invalid"


def test_explain_error_falls_back_to_generic_hint():
    assert explain_error(ValueError("boom"), "兜底提示") == "兜底提示"
    assert explain_error(FloodWaitError(None, 7), "兜底提示") == "Telegram 要求等待 7 秒后再试"
    assert explain_error(ConnectionError("boom"), "兜底提示").startswith("无法连接 Telegram")


@pytest.mark.asyncio
@pytest.mark.parametrize(("error", "expected_hint"), [
    (PhoneNumberInvalidError(None), "国家码"),
    (ApiIdInvalidError(None), "TG_API_ID"),
    (AuthKeyUnregisteredError(None), "session 已失效"),
    (ConnectionError("boom"), "TG_PROXY_URL"),
])
async def test_login_surfaces_reason_and_error_class(tmp_path, monkeypatch, error, expected_hint):
    install_fake_client(monkeypatch, error=error)
    manager = TelegramManager(build_settings(tmp_path))
    with pytest.raises(AppError) as caught:
        await manager.login("+8613800000000")
    assert caught.value.code == "telegram_login_failed"
    assert expected_hint in caught.value.message
    assert caught.value.detail == type(error).__name__
    assert manager.last_error == type(error).__name__


@pytest.mark.asyncio
async def test_login_reports_flood_wait_seconds(tmp_path, monkeypatch):
    install_fake_client(monkeypatch, error=FloodWaitError(None, 42))
    manager = TelegramManager(build_settings(tmp_path))
    with pytest.raises(AppError) as caught:
        await manager.login("+8613800000000")
    assert "42" in caught.value.message
    assert caught.value.detail == "FloodWaitError"


# --------------------------------------------------------------------- 连接与断线


@pytest.mark.asyncio
async def test_manual_disconnect_does_not_silently_reconnect(tmp_path, monkeypatch):
    install_fake_client(monkeypatch, authorized=True)
    legacy_session(tmp_path)
    manager = TelegramManager(build_settings(tmp_path))
    await manager.connect()
    await manager.disconnect()
    with pytest.raises(AppError):
        await manager.require_authorized()
    await manager.reconnect()
    assert (await manager.status()).authorized


@pytest.mark.asyncio
async def test_connect_without_any_session_reports_missing_account(tmp_path, monkeypatch):
    install_fake_client(monkeypatch)
    manager = TelegramManager(build_settings(tmp_path))
    with pytest.raises(AppError) as caught:
        await manager.connect()
    assert caught.value.code == "telegram_no_account"


@pytest.mark.asyncio
async def test_telegram_client_uses_configured_http_proxy(tmp_path, monkeypatch):
    async def connect_without_network(self):
        return None

    monkeypatch.setattr(TelegramClient, "connect", connect_without_network)
    legacy_session(tmp_path)
    manager = TelegramManager(build_settings(tmp_path, tg_proxy_url="http://127.0.0.1:10809"))

    await manager.connect()

    assert manager.client is not None
    assert manager.client._proxy == ("http", "127.0.0.1", 10809)


@pytest.mark.parametrize("proxy_url", ["http:127.0.0.1:10809", "https://127.0.0.1:10809",
                                       "http://127.0.0.1", "http://127.0.0.1:10809/path"])
def test_invalid_telegram_proxy_url_is_rejected(proxy_url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tg_proxy_url=proxy_url)


# --------------------------------------------------------------------- 多账号 session


@pytest.mark.asyncio
async def test_login_binds_phone_to_its_own_session(tmp_path, monkeypatch):
    created = install_fake_client(monkeypatch)
    manager = TelegramManager(build_settings(tmp_path))

    await manager.login("+8613800000000")

    assert created[0].args[0] == str(tmp_path / "accounts" / "8613800000000" / "telegram")
    assert read_index(tmp_path)["active"] == "8613800000000"


@pytest.mark.asyncio
async def test_login_switches_client_between_accounts(tmp_path, monkeypatch):
    created = install_fake_client(monkeypatch)
    manager = TelegramManager(build_settings(tmp_path))

    await manager.login("+8613800000000")
    await manager.login("+8613900000000")

    assert created[0].args[0] != created[1].args[0]
    assert created[0].disconnects == 1
    assert created[1].code_requests == ["+8613900000000"]
    assert read_index(tmp_path)["active"] == "8613900000000"


@pytest.mark.asyncio
async def test_legacy_session_is_reused_as_existing_account(tmp_path, monkeypatch):
    legacy_session(tmp_path)
    created = install_fake_client(monkeypatch, authorized=True)
    manager = TelegramManager(build_settings(tmp_path))

    await manager.connect()

    assert created[0].args[0] == str(tmp_path / "telegram")
    accounts = manager.accounts()
    assert [item.key for item in accounts] == ["legacy"]
    assert accounts[0].active and accounts[0].legacy


@pytest.mark.asyncio
async def test_activate_switches_active_account(tmp_path, monkeypatch):
    legacy_session(tmp_path)
    account_session(tmp_path, "8613800000000")
    created = install_fake_client(monkeypatch, authorized=True)
    manager = TelegramManager(build_settings(tmp_path))

    status = await manager.activate("8613800000000")

    assert status.account == "8613800000000"
    assert created[-1].args[0] == str(tmp_path / "accounts" / "8613800000000" / "telegram")
    assert read_index(tmp_path)["active"] == "8613800000000"
    with pytest.raises(AppError) as caught:
        await manager.activate("999")
    assert caught.value.code == "account_not_found"


@pytest.mark.asyncio
async def test_remove_account_deletes_local_session_only(tmp_path, monkeypatch):
    install_fake_client(monkeypatch)
    manager = TelegramManager(build_settings(tmp_path))
    await manager.login("+8613800000000")
    path = tmp_path / "accounts" / "8613800000000" / "telegram.session"
    path.write_text("x", encoding="utf-8")

    await manager.remove_account("8613800000000")

    assert not path.exists()
    assert manager.accounts() == []


@pytest.mark.asyncio
async def test_status_records_account_identity_in_index(tmp_path, monkeypatch):
    legacy_session(tmp_path)
    me = SimpleNamespace(id=42, first_name="敖", last_name="烈", username="aole", phone="8615684167371")
    install_fake_client(monkeypatch, authorized=True, me=me)
    manager = TelegramManager(build_settings(tmp_path))

    await manager.connect()
    status = await manager.status()

    assert status.account == "legacy"
    assert status.account_name == "敖 烈"
    assert read_index(tmp_path)["accounts"]["legacy"]["phone"] == "+8615684167371"
