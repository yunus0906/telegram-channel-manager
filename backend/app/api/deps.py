import re

from fastapi import Depends, Request
from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import Channel


def parse_telegram_id(value: str, *, positive: bool = False) -> int:
    if not re.fullmatch(r"-?\d{1,20}", value):
        raise AppError(422, "invalid_telegram_id", "Telegram ID 格式无效")
    parsed = int(value)
    if not -(2 ** 63) <= parsed < 2 ** 63 or (positive and parsed <= 0):
        raise AppError(422, "invalid_telegram_id", "Telegram ID 超出范围")
    return parsed


async def require_admin(request: Request) -> str:
    token = request.cookies.get("tcm_session")
    if not await request.app.state.auth.valid(token):
        raise AppError(401, "unauthorized", "请先登录管理员账号")
    assert token is not None
    return token


async def require_csrf(request: Request, token: str = Depends(require_admin)) -> str:
    if not request.app.state.auth.check_csrf(token, request.headers.get("X-CSRF-Token")):
        raise AppError(403, "csrf_invalid", "请求验证失败，请刷新页面重试")
    return token


async def managed_channel(request: Request, channel_id: str) -> Channel:
    chat_id = parse_telegram_id(channel_id)
    async with request.app.state.db.sessions() as session:
        row = await session.scalar(select(Channel).where(Channel.telegram_chat_id == chat_id, Channel.is_managed.is_(True)))
        if row is None:
            raise AppError(404, "channel_not_found", "频道不存在")
        return row

