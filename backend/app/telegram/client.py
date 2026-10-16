import asyncio
import contextlib
import getpass
import json
import logging
import os
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events, utils
from telethon.errors import (
    ApiIdInvalidError,
    ApiIdPublishedFloodError,
    AuthKeyDuplicatedError,
    AuthKeyUnregisteredError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeHashEmptyError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    SessionRevokedError,
)

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.api import AvailableChannel, TelegramAccount, TelegramStatus


logger = logging.getLogger(__name__)
MessageCallback = Callable[[int, Any], Awaitable[None]]

ACCOUNTS_DIR_NAME = "accounts"
LEGACY_ACCOUNT = "legacy"
INDEX_FILE_NAME = "index.json"
SESSION_BASENAME = "telegram"

PHONE_FORMAT_HINT = "手机号格式不正确，请使用带国家码的国际格式，例如 +8613800000000"
SESSION_RESET_HINT = "本地 Telegram session 已失效，请移除该账号后重新登录"
CONNECTION_HINT = "无法连接 Telegram，请检查网络与 TG_PROXY_URL 代理设置"

_TELEGRAM_ERROR_HINTS: dict[type[BaseException], str] = {
    PhoneNumberInvalidError: PHONE_FORMAT_HINT,
    PhoneNumberBannedError: "该手机号已被 Telegram 封禁，无法登录",
    PhoneNumberFloodError: "该手机号请求验证码过于频繁，请等待 24 小时后重试",
    ApiIdInvalidError: "TG_API_ID 或 TG_API_HASH 无效，请检查 backend/.env",
    ApiIdPublishedFloodError: "该 API 凭证已被 Telegram 判定为公开（常见于从教程或仓库抄来的凭证），请更换为自己的凭证",
    AuthKeyUnregisteredError: SESSION_RESET_HINT,
    SessionRevokedError: SESSION_RESET_HINT,
    AuthKeyDuplicatedError: "同一 session 文件被多个进程同时使用，请确认只运行一个后端进程",
    PhoneCodeInvalidError: "验证码不正确",
    PhoneCodeExpiredError: "验证码已过期，请重新发送",
    PhoneCodeEmptyError: "验证码为空，请重新输入",
    PhoneCodeHashEmptyError: "验证码会话已失效，请重新发送验证码",
    PasswordHashInvalidError: "两步验证密码不正确",
}


def explain_error(exc: BaseException, fallback: str) -> str:
    """把 Telethon 异常翻译成可执行的排查提示。

    只使用异常类别层面的信息，不会带回手机号、验证码、密码或 API Hash。
    """
    if isinstance(exc, FloodWaitError):
        return f"Telegram 要求等待 {exc.seconds} 秒后再试"
    for error_type, hint in _TELEGRAM_ERROR_HINTS.items():
        if isinstance(exc, error_type):
            return hint
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return CONNECTION_HINT
    return fallback


def account_key(phone: str) -> str:
    """把用户输入的电话号码归一化成账号目录名（纯数字的国际格式）。

    必须显式带国家码，否则 Telegram 会把它当成别的国家号码 —— 这正是
    "请求验证码失败" 最常见的原因，所以在本地就拦掉。
    """
    raw = (phone or "").strip()
    if not raw.startswith("+"):
        raise AppError(422, "phone_country_code_required", "手机号必须以国家码开头，例如 +8613800000000")
    digits = utils.parse_phone(raw)
    if not digits or not 8 <= len(digits) <= 15:
        raise AppError(422, "phone_invalid", PHONE_FORMAT_HINT)
    return digits


class TelegramManager:
    """单进程内只保留一个 Telethon 客户端；每个手机号各自拥有一份 session 文件。

    已登录账号的 session 再对它自己请求验证码是无害的，但 Telethon 的 `sign_in()`
    在已授权时会直接返回旧用户，因此同一个 session 无法切换到别的账号。把 session
    按手机号拆开之后，登录新账号用的是全新的空 session，`sign_in()` 才能正常生效。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: TelegramClient | None = None
        self._lock = asyncio.Lock()
        self._active: str | None = None
        self._phone: str | None = None
        self._needs_password = False
        self._manual_disconnect = False
        self.last_error: str | None = None
        self._on_new: MessageCallback | None = None
        self._on_edit: MessageCallback | None = None
        self._entities: dict[int, Any] = {}
        self._identity_loaded: set[str] = set()

    def set_handlers(self, on_new: MessageCallback, on_edit: MessageCallback) -> None:
        self._on_new = on_new
        self._on_edit = on_edit

    @property
    def configured(self) -> bool:
        return bool(self.settings.tg_api_id and self.settings.tg_api_hash)

    @property
    def manual_disconnect(self) -> bool:
        return self._manual_disconnect

    # ------------------------------------------------------------------ 账号存储

    def _index_path(self) -> Path:
        return self.settings.data_root / ACCOUNTS_DIR_NAME / INDEX_FILE_NAME

    def _read_index(self) -> dict[str, Any]:
        try:
            data = json.loads(self._index_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_index(self, index: dict[str, Any]) -> None:
        path = self._index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _persist_active(self, key: str | None) -> None:
        index = self._read_index()
        index["active"] = key
        index.setdefault("accounts", {})
        self._write_index(index)

    def _session_base(self, key: str) -> Path:
        if key == LEGACY_ACCOUNT:
            return self.settings.data_root / SESSION_BASENAME
        return self.settings.data_root / ACCOUNTS_DIR_NAME / key / SESSION_BASENAME

    def _has_session(self, key: str) -> bool:
        return Path(f"{self._session_base(key)}.session").exists()

    def _discover_keys(self) -> list[str]:
        """磁盘上真实存在 session 文件的账号，旧版单文件 session 排在第一位。"""
        keys: list[str] = []
        if self._has_session(LEGACY_ACCOUNT):
            keys.append(LEGACY_ACCOUNT)
        accounts_dir = self.settings.data_root / ACCOUNTS_DIR_NAME
        if accounts_dir.is_dir():
            for entry in sorted(accounts_dir.iterdir()):
                if entry.is_dir() and Path(f"{entry / SESSION_BASENAME}.session").exists():
                    keys.append(entry.name)
        return keys

    def _resolve_active(self) -> str | None:
        """当前活动账号：优先用内存值，其次索引，最后按磁盘上的 session 推断。"""
        if self._active is not None:
            return self._active
        stored = self._read_index().get("active")
        if isinstance(stored, str) and stored != LEGACY_ACCOUNT and self._has_session(stored):
            self._active = stored
            return self._active
        if stored == LEGACY_ACCOUNT and self._has_session(LEGACY_ACCOUNT):
            self._active = LEGACY_ACCOUNT
            return self._active
        keys = self._discover_keys()
        self._active = keys[0] if keys else None
        return self._active

    def _account_meta(self, key: str) -> dict[str, Any]:
        meta = (self._read_index().get("accounts") or {}).get(key)
        return meta if isinstance(meta, dict) else {}

    def accounts(self) -> list[TelegramAccount]:
        active = self._resolve_active()
        index = self._read_index().get("accounts") or {}
        keys = self._discover_keys()
        for key in index:
            if key not in keys:
                keys.append(key)
        result: list[TelegramAccount] = []
        for key in keys:
            meta = self._account_meta(key)
            phone = meta.get("phone") or (None if key == LEGACY_ACCOUNT else f"+{key}")
            result.append(TelegramAccount(key=key, phone=phone, name=meta.get("name"),
                                          username=meta.get("username"), active=key == active,
                                          legacy=key == LEGACY_ACCOUNT))
        return result

    def _secure_session(self) -> None:
        key = self._resolve_active()
        if key is None:
            return
        session_path = Path(f"{self._session_base(key)}.session")
        if not session_path.exists():
            return
        if os.name == "nt":
            try:
                subprocess.run(["icacls", str(session_path), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:(R,W)"], check=True, capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                logger.warning("无法设置 Telegram session 文件 ACL")
        else:
            session_path.chmod(0o600)

    async def _reset_client(self) -> None:
        """断开并丢弃当前客户端，让下一次 connect 绑定到新的账号 session。"""
        if self.client is not None:
            with contextlib.suppress(Exception):
                await self.client.disconnect()
        self.client = None
        self._entities.clear()
        self._phone = None
        self._needs_password = False

    async def _refresh_identity(self) -> None:
        """把已授权账号的昵称和手机号记进索引，供账号列表展示。"""
        key = self._resolve_active()
        if key is None or key in self._identity_loaded or self.client is None:
            return
        try:
            if not await asyncio.wait_for(self.client.is_user_authorized(), timeout=5):
                return
            user = await asyncio.wait_for(self.client.get_me(), timeout=15)
        except Exception as exc:
            logger.warning("读取 Telegram 账号信息失败: %s", type(exc).__name__)
            return
        if user is None:
            return
        self._identity_loaded.add(key)
        index = self._read_index()
        entry = index.setdefault("accounts", {}).setdefault(key, {})
        if not isinstance(entry, dict):
            entry = {}
            index["accounts"][key] = entry
        entry.update({
            "name": " ".join(filter(None, [user.first_name, user.last_name])) or entry.get("name"),
            "username": user.username,
            "user_id": str(user.id),
        })
        if getattr(user, "phone", None):
            entry["phone"] = f"+{user.phone}"
        if entry.get("phone") and key == LEGACY_ACCOUNT:
            entry["legacy"] = True
        self._write_index(index)

    # ------------------------------------------------------------------ 连接与登录

    async def connect(self, *, force: bool = False) -> None:
        if not self.configured:
            raise AppError(503, "telegram_not_configured", "请先配置 TG_API_ID 和 TG_API_HASH")
        if self._manual_disconnect and not force:
            raise AppError(409, "telegram_disconnected", "Telegram 已手动断开，请先重新连接")
        if force:
            self._manual_disconnect = False
        async with self._lock:
            if self.client is None:
                key = self._resolve_active()
                if key is None:
                    raise AppError(409, "telegram_no_account", "尚未登录任何 Telegram 账号，请先在设置页登录")
                base = self._session_base(key)
                base.parent.mkdir(parents=True, exist_ok=True)
                self.client = TelegramClient(str(base), self.settings.tg_api_id,
                                             self.settings.tg_api_hash, proxy=self.settings.telegram_proxy)
                self.client.add_event_handler(self._new_event, events.NewMessage())
                self.client.add_event_handler(self._edit_event, events.MessageEdited())
            if not self.client.is_connected():
                try:
                    await asyncio.wait_for(self.client.connect(), timeout=15)
                    self._secure_session()
                    self.last_error = None
                except Exception as exc:
                    self.last_error = type(exc).__name__
                    logger.warning("Telegram 连接失败: %s", type(exc).__name__, exc_info=True)
                    raise AppError(503, "telegram_connect_failed", explain_error(exc, "Telegram 连接失败"),
                                   type(exc).__name__) from exc

    async def status(self) -> TelegramStatus:
        connected = bool(self.client and self.client.is_connected())
        authorized = False
        if connected and self.client:
            try:
                authorized = await asyncio.wait_for(self.client.is_user_authorized(), timeout=5)
            except Exception as exc:
                self.last_error = type(exc).__name__
        key = self._resolve_active()
        if authorized:
            await self._refresh_identity()
        meta = self._account_meta(key) if key else {}
        return TelegramStatus(connected=connected, authorized=authorized, configured=self.configured,
                              last_error=self.last_error, needs_password=self._needs_password,
                              account=key, account_name=meta.get("name"))

    async def require_authorized(self) -> TelegramClient:
        await self.connect()
        assert self.client is not None
        if not await asyncio.wait_for(self.client.is_user_authorized(), timeout=10):
            raise AppError(409, "telegram_unauthorized", "请先完成 Telegram 授权")
        return self.client

    async def activate(self, key: str) -> TelegramStatus:
        """切换到指定账号（复用本地已有 session，不重新登录）。"""
        known = key in self._discover_keys() or key in (self._read_index().get("accounts") or {})
        if not known:
            raise AppError(404, "account_not_found", "该账号在本地没有 session")
        if key == self._resolve_active() and self.client is not None and self.client.is_connected():
            return await self.status()
        await self._reset_client()
        self._active = key
        self._persist_active(key)
        self._manual_disconnect = False
        await self.connect(force=True)
        await self._refresh_identity()
        return await self.status()

    async def remove_account(self, key: str) -> None:
        """删除账号的本地 session 文件。

        只清本地：Telegram 端的登录态仍在，需要用户到「已登录设备」里自行移除。
        """
        if key not in self._discover_keys():
            raise AppError(404, "account_not_found", "该账号在本地没有 session")
        if key == self._resolve_active():
            await self._reset_client()
            self._active = None
        base = self._session_base(key)
        for suffix in (".session", ".session-journal", ".session-wal"):
            with contextlib.suppress(OSError):
                Path(f"{base}{suffix}").unlink()
        index = self._read_index()
        (index.get("accounts") or {}).pop(key, None)
        if index.get("active") == key:
            index["active"] = None
        self._write_index(index)
        self._identity_loaded.discard(key)
        logger.info("已移除本地 Telegram session: %s", key)

    async def login(self, phone: str) -> TelegramStatus:
        key = account_key(phone)
        if key != self._resolve_active() or self.client is None:
            await self._reset_client()
            self._active = key
            self._persist_active(key)
        await self.connect(force=True)
        assert self.client is not None
        self._phone = phone
        self._needs_password = False
        try:
            await asyncio.wait_for(self.client.send_code_request(phone), timeout=30)
        except Exception as exc:
            self.last_error = type(exc).__name__
            logger.warning("Telegram 请求验证码失败: %s", type(exc).__name__, exc_info=True)
            raise AppError(502, "telegram_login_failed", explain_error(exc, "请求验证码失败，请检查连接和手机号"),
                           type(exc).__name__) from exc
        self._secure_session()
        return await self.status()

    async def verify(self, code: str | None, password: str | None) -> TelegramStatus:
        await self.connect()
        assert self.client is not None
        try:
            if self._needs_password:
                if not password:
                    raise AppError(422, "password_required", "请输入两步验证密码")
                await asyncio.wait_for(self.client.sign_in(password=password), timeout=30)
            else:
                if not self._phone or not code:
                    raise AppError(422, "code_required", "请先请求并输入验证码")
                await asyncio.wait_for(self.client.sign_in(phone=self._phone, code=code), timeout=30)
        except SessionPasswordNeededError:
            self._needs_password = True
            return await self.status()
        except AppError:
            raise
        except Exception as exc:
            self.last_error = type(exc).__name__
            logger.warning("Telegram 验证失败: %s", type(exc).__name__, exc_info=True)
            raise AppError(400, "telegram_verify_failed", explain_error(exc, "Telegram 验证失败，请检查验证码或密码"),
                           type(exc).__name__) from exc
        self._phone = None
        self._needs_password = False
        self._secure_session()
        self._identity_loaded.discard(self._resolve_active() or "")
        return await self.status()

    async def disconnect(self) -> TelegramStatus:
        self._manual_disconnect = True
        if self.client:
            await self.client.disconnect()
        return await self.status()

    async def reconnect(self) -> TelegramStatus:
        await self.connect(force=True)
        return await self.status()

    async def me(self) -> dict[str, str | None]:
        client = await self.require_authorized()
        user = await asyncio.wait_for(client.get_me(), timeout=15)
        return {"id": str(user.id), "username": user.username, "name": " ".join(filter(None, [user.first_name, user.last_name]))}

    async def discover(self) -> list[AvailableChannel]:
        client = await self.require_authorized()
        result: list[AvailableChannel] = []
        try:
            async with asyncio.timeout(30):
                async for dialog in client.iter_dialogs():
                    if not dialog.is_channel:
                        continue
                    entity = dialog.entity
                    chat_id = int(utils.get_peer_id(entity))
                    self._entities[chat_id] = entity
                    username = getattr(entity, "username", None)
                    result.append(AvailableChannel(
                        telegram_chat_id=str(chat_id), title=dialog.name,
                        username=username, access_type="public" if username else "private",
                        channel_type="megagroup" if getattr(entity, "megagroup", False) else "broadcast",
                        permalink=f"https://t.me/{username}" if username else None,
                    ))
        except Exception as exc:
            self.last_error = type(exc).__name__
            logger.warning("读取 Telegram 频道失败: %s", type(exc).__name__, exc_info=True)
            raise AppError(503, "telegram_discovery_failed",
                           explain_error(exc, "无法读取当前账号频道，请检查连接和访问权限"),
                           type(exc).__name__) from exc
        return result

    async def resolve_accessible(self, chat_id: int) -> AvailableChannel:
        channels = await self.discover()
        for channel in channels:
            if int(channel.telegram_chat_id) == chat_id:
                return channel
        raise AppError(403, "channel_inaccessible", "当前账号无法访问此频道")

    async def entity(self, chat_id: int) -> Any:
        if chat_id not in self._entities:
            await self.resolve_accessible(chat_id)
        return self._entities[chat_id]

    async def get_message(self, chat_id: int, message_id: int) -> Any:
        client = await self.require_authorized()
        result = await asyncio.wait_for(client.get_messages(await self.entity(chat_id), ids=message_id), timeout=30)
        if result is None:
            raise AppError(404, "telegram_message_missing", "Telegram 消息已不可访问")
        return result

    async def _new_event(self, event: Any) -> None:
        if self._on_new and event.chat_id:
            await self._on_new(int(event.chat_id), event.message)

    async def _edit_event(self, event: Any) -> None:
        if self._on_edit and event.chat_id:
            await self._on_edit(int(event.chat_id), event.message)
