from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import managed_channel, require_admin, require_csrf
from app.api.tasks import task_out
from app.core.errors import AppError
from app.db.models import SyncTask
from app.schemas.api import ExportCreate, Page, TaskOut


router = APIRouter(prefix="/exports", tags=["exports"])
EXPORT_TYPES = ("json_export", "jsonl_export", "zip_export")


@router.post("", response_model=TaskOut, status_code=202, dependencies=[Depends(require_csrf)])
async def create_export(data: ExportCreate, request: Request) -> TaskOut:
    ip = request.client.host if request.client else "unknown"
    if not request.app.state.limiter.allow(f"export:{ip}", 10, 3600):
        raise AppError(429, "rate_limited", "导出操作过于频繁，请稍后再试")
    if data.date_from and data.date_to and data.date_from > data.date_to:
        raise AppError(422, "invalid_date_range", "开始日期不能晚于结束日期")
    if data.media_only and (data.format != "zip" or not data.include_media or not data.telegram_chat_id):
        raise AppError(422, "invalid_export_options", "仅媒体 ZIP 需要指定频道并包含媒体")
    channel_id = None
    if data.telegram_chat_id:
        channel_id = (await managed_channel(request, data.telegram_chat_id)).id
    kind = {"json": "json_export", "jsonl": "jsonl_export", "zip": "zip_export"}[data.format]
    options = {"include_media": data.include_media, "media_only": data.media_only,
               "date_from": data.date_from.isoformat() if data.date_from else None,
               "date_to": data.date_to.isoformat() if data.date_to else None}
    task, _ = await request.app.state.tasks.create(kind, channel_id, options)
    return await task_out(request, task)


@router.get("", response_model=Page[TaskOut], dependencies=[Depends(require_admin)])
async def list_exports(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> Page[TaskOut]:
    stmt = select(SyncTask).where(SyncTask.task_type.in_(EXPORT_TYPES))
    async with request.app.state.db.sessions() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (await session.scalars(stmt.order_by(SyncTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return Page(items=[await task_out(request, row) for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{export_id}", response_model=TaskOut, dependencies=[Depends(require_admin)])
async def get_export(export_id: str, request: Request) -> TaskOut:
    task = await request.app.state.tasks.get(export_id)
    if task.task_type not in EXPORT_TYPES:
        raise AppError(404, "export_not_found", "导出任务不存在")
    return await task_out(request, task)


@router.get("/{export_id}/download", dependencies=[Depends(require_admin)])
async def download_export(export_id: str, request: Request) -> FileResponse:
    task = await request.app.state.tasks.get(export_id)
    if task.task_type not in EXPORT_TYPES:
        raise AppError(404, "export_not_found", "导出任务不存在")
    path = await request.app.state.exports.download_path(task)
    return FileResponse(path, filename=path.name)

