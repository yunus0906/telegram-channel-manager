import asyncio
import getpass
import logging
import os
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from telethon import TelegramClient, events, utils
from telethon.errors import SessionPasswordNeededError

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.api import AvailableChannel, TelegramStatus


logger = logging.getLogger(__name__)
MessageCallback = Callable[[int, Any], Awaitable[None]]


class TelegramManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: TelegramClient | None = None
        self._lock = asyncio.Lock()
        self._phone: str | None = None
        self._needs_password = False
        self._manual_disconnect = False
        self.last_error: str | None = None
        self._on_new: MessageCallback | None = None
        self._on_edit: MessageCallback | None = None
        self._entities: dict[int, Any] = {}

    def set_handlers(self, on_new: MessageCallback, on_edit: MessageCallback) -> None:
        self._on_new = on_new
        self._on_edit = on_edit

    @property
    def configured(self) -> bool:
        return bool(self.settings.tg_api_id and self.settings.tg_api_hash)

    @property
    def manual_disconnect(self) -> bool:
        return self._manual_disconnect

    def _secure_session(self) -> None:
        session_path = self.settings.data_root / "telegram.session"
        if not session_path.exists():
            return
        if os.name == "nt":
            try:
                subprocess.run(["icacls", str(session_path), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:(R,W)"], check=True, capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                logger.warning("无法设置 Telegram session 文件 ACL")
        else:
            session_path.chmod(0o600)

    async def connect(self, *, force: bool = False) -> None:
        if not self.configured:
            raise AppError(503, "telegram_not_configured", "请先配置 TG_API_ID 和 TG_API_HASH")
        if self._manual_disconnect and not force:
            raise AppError(409, "telegram_disconnected", "Telegram 已手动断开，请先重新连接")
        if force:
            self._manual_disconnect = False
        async with self._lock:
            if self.client is None:
                self.settings.data_root.mkdir(parents=True, exist_ok=True)
                self.client = TelegramClient(str(self.settings.data_root / "telegram"), self.settings.tg_api_id,
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
                    raise AppError(503, "telegram_connect_failed", "Telegram 连接失败") from exc

    async def status(self) -> TelegramStatus:
        connected = bool(self.client and self.client.is_connected())
        authorized = False
        if connected and self.client:
            try:
                authorized = await asyncio.wait_for(self.client.is_user_authorized(), timeout=5)
            except Exception as exc:
                self.last_error = type(exc).__name__
        return TelegramStatus(connected=connected, authorized=authorized, configured=self.configured,
                              last_error=self.last_error, needs_password=self._needs_password)

    async def require_authorized(self) -> TelegramClient:
        await self.connect()
        assert self.client is not None
        if not await asyncio.wait_for(self.client.is_user_authorized(), timeout=10):
            raise AppError(409, "telegram_unauthorized", "请先完成 Telegram 授权")
        return self.client

    async def login(self, phone: str) -> TelegramStatus:
        await self.connect(force=True)
        assert self.client is not None
        self._phone = phone
        self._needs_password = False
        try:
            await asyncio.wait_for(self.client.send_code_request(phone), timeout=30)
        except Exception as exc:
            self.last_error = type(exc).__name__
            raise AppError(502, "telegram_login_failed", "请求验证码失败，请检查连接和手机号") from exc
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
            raise AppError(400, "telegram_verify_failed", "Telegram 验证失败，请检查验证码或密码") from exc
        self._phone = None
        self._needs_password = False
        self._secure_session()
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
            raise AppError(503, "telegram_discovery_failed", "无法读取当前账号频道，请检查连接和访问权限") from exc
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

