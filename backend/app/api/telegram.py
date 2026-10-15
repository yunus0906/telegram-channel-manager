import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_admin, require_csrf
from app.core.errors import AppError
from app.schemas.api import TelegramLoginIn, TelegramMe, TelegramStatus, TelegramVerifyIn


router = APIRouter(prefix="/telegram", tags=["telegram"])


async def publish_status(request: Request, status: TelegramStatus) -> None:
    await request.app.state.hub.publish({"event_id": str(uuid.uuid4()), "type": "telegram.connection",
                                         "channel_id": None, "message_id": None, "timestamp": None,
                                         "data": status.model_dump()})


@router.get("/status", response_model=TelegramStatus, dependencies=[Depends(require_admin)])
async def status(request: Request) -> TelegramStatus:
    return await request.app.state.telegram.status()


@router.post("/login", response_model=TelegramStatus, dependencies=[Depends(require_csrf)])
async def login(data: TelegramLoginIn, request: Request) -> TelegramStatus:
    ip = request.client.host if request.client else "unknown"
    if not request.app.state.limiter.allow(f"telegram-login:{ip}", 5, 600):
        raise AppError(429, "rate_limited", "请求验证码过于频繁，请稍后再试")
    result = await request.app.state.telegram.login(data.phone)
    await publish_status(request, result)
    return result


@router.post("/login/verify", response_model=TelegramStatus, dependencies=[Depends(require_csrf)])
async def verify(data: TelegramVerifyIn, request: Request) -> TelegramStatus:
    ip = request.client.host if request.client else "unknown"
    if not request.app.state.limiter.allow(f"telegram-verify:{ip}", 5, 600):
        raise AppError(429, "rate_limited", "验证尝试过于频繁，请稍后再试")
    result = await request.app.state.telegram.verify(data.code, data.password)
    await publish_status(request, result)
    return result


@router.post("/disconnect", response_model=TelegramStatus, dependencies=[Depends(require_csrf)])
async def disconnect(request: Request) -> TelegramStatus:
    result = await request.app.state.telegram.disconnect()
    await publish_status(request, result)
    return result


@router.post("/reconnect", response_model=TelegramStatus, dependencies=[Depends(require_csrf)])
async def reconnect(request: Request) -> TelegramStatus:
    result = await request.app.state.telegram.reconnect()
    await publish_status(request, result)
    return result


@router.get("/me", response_model=TelegramMe, dependencies=[Depends(require_admin)])
async def telegram_me(request: Request) -> TelegramMe:
    return TelegramMe.model_validate(await request.app.state.telegram.me())

