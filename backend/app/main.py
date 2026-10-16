import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, channels, dashboard, exports, messages, settings as settings_api, tasks, telegram
from app.core.auth import AuthService, RateLimiter
from app.core.config import Settings, get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import configure_logging, set_log_level
from app.db.session import Database
from app.schemas.api import Health
from app.services.export_service import ExportService
from app.services.media_service import MediaService
from app.services.message_store import MessageStore
from app.services.settings_service import SettingsService
from app.services.tasks import TaskService
from app.telegram.client import TelegramManager
from app.websocket.hub import EventHub
from app.workers.runner import TaskRunner


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if not settings.admin_password_hash or len(settings.session_secret) < 16:
        raise RuntimeError("必须配置 ADMIN_PASSWORD_HASH 和至少 16 字符的 SESSION_SECRET")
    if settings.host not in {"127.0.0.1", "localhost", "::1"} and not settings.cookie_secure:
        raise RuntimeError("非本机监听必须启用 COOKIE_SECURE 并使用 HTTPS 反向代理")

    log_file = configure_logging(settings)

    db = Database(settings)
    hub = EventHub()
    telegram_manager = TelegramManager(settings)
    store = MessageStore(db.sessions)
    task_service = TaskService(db.sessions)
    app_settings = SettingsService(db.sessions)
    export_service = ExportService(settings, db.sessions, app_settings)
    media_service = MediaService(settings, db.sessions, app_settings, telegram_manager, hub)
    runner = TaskRunner(db.sessions, telegram_manager, store, task_service, export_service, media_service, app_settings, hub)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(db.migrate)
        set_log_level((await app_settings.get()).values.log_level)
        await runner.start()
        try:
            yield
        finally:
            await runner.stop()
            await db.close()

    app = FastAPI(title="Telegram Channel Manager", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.log_file = str(log_file)
    app.state.db = db
    app.state.hub = hub
    app.state.telegram = telegram_manager
    app.state.store = store
    app.state.tasks = task_service
    app.state.app_settings = app_settings
    app.state.exports = export_service
    app.state.media = media_service
    app.state.runner = runner
    app.state.auth = AuthService(settings, db.sessions)
    app.state.limiter = RateLimiter()
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in settings.allowed_origins:
            return JSONResponse(status_code=403, content={"error": {"code": "origin_forbidden", "message": "请求来源不被允许"}})
        return await call_next(request)

    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "请求参数无效"}})

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail)}})

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        logger.error("请求处理失败: %s", type(exc).__name__, exc_info=True)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "服务器处理请求失败"}})

    @app.get("/api/v1/health", response_model=Health)
    async def health() -> Health:
        return Health()

    for router in (auth.router, telegram.router, channels.router, messages.router, tasks.router,
                   exports.router, settings_api.router, dashboard.router):
        app.include_router(router, prefix="/api/v1")

    @app.websocket("/api/v1/ws")
    async def websocket_endpoint(socket: WebSocket):
        origin = socket.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            await socket.close(code=4403)
            return
        if not await app.state.auth.valid(socket.cookies.get("tcm_session")):
            await socket.close(code=4401)
            return
        await socket.accept()
        try:
            await hub.serve(socket)
        except (WebSocketDisconnect, RuntimeError):
            pass

    return app
