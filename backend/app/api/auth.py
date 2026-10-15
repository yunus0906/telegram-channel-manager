from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import require_csrf
from app.core.errors import AppError
from app.schemas.api import ActionResult, AuthLoginIn, AuthMe


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthMe)
async def login(data: AuthLoginIn, request: Request, response: Response) -> AuthMe:
    ip = request.client.host if request.client else "unknown"
    if not request.app.state.limiter.allow(f"admin-login:{ip}", 5, 600):
        raise AppError(429, "rate_limited", "登录尝试过于频繁，请稍后再试")
    token = await request.app.state.auth.login(data.password)
    if token is None:
        raise AppError(401, "invalid_credentials", "管理员密码错误")
    response.set_cookie("tcm_session", token, httponly=True, secure=request.app.state.settings.cookie_secure,
                        samesite="strict", max_age=12 * 3600, path="/api/v1")
    return AuthMe(authenticated=True, csrf_token=request.app.state.auth.csrf(token))


@router.get("/me", response_model=AuthMe)
async def me(request: Request) -> AuthMe:
    token = request.cookies.get("tcm_session")
    if not await request.app.state.auth.valid(token):
        raise AppError(401, "unauthorized", "请先登录管理员账号")
    return AuthMe(authenticated=True, csrf_token=request.app.state.auth.csrf(token))


@router.post("/logout", response_model=ActionResult, dependencies=[Depends(require_csrf)])
async def logout(request: Request, response: Response) -> ActionResult:
    await request.app.state.auth.logout(request.cookies.get("tcm_session"))
    response.delete_cookie("tcm_session", path="/api/v1")
    return ActionResult()

