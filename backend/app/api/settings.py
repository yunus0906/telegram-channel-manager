import logging

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_admin, require_csrf
from app.core.errors import AppError
from app.schemas.api import AppSettingsSchema, SettingsOut


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut, dependencies=[Depends(require_admin)])
async def get_settings(request: Request) -> SettingsOut:
    return await request.app.state.app_settings.get()


@router.put("", response_model=SettingsOut, dependencies=[Depends(require_csrf)])
async def put_settings(data: AppSettingsSchema, request: Request) -> SettingsOut:
    try:
        result = await request.app.state.app_settings.put(data)
    except ValueError as exc:
        raise AppError(422, "invalid_directory", "目录必须是数据根目录内的安全相对路径") from exc
    logging.getLogger().setLevel(data.log_level)
    return result

