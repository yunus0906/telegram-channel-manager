from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import parse_telegram_id, require_admin, require_csrf
from app.db.models import Channel, SyncTask, as_utc
from app.schemas.api import Page, TaskOut


router = APIRouter(prefix="/tasks", tags=["tasks"])


async def task_out(request: Request, task: SyncTask) -> TaskOut:
    chat_id = None
    if task.channel_id:
        async with request.app.state.db.sessions() as session:
            channel = await session.get(Channel, task.channel_id)
            chat_id = str(channel.telegram_chat_id) if channel else None
    return TaskOut(
        id=task.id, telegram_chat_id=chat_id, task_type=task.task_type, status=task.status,
        cursor_message_id=str(task.cursor_message_id) if task.cursor_message_id is not None else None,
        processed_count=task.processed_count, total_count=task.total_count, error_message=task.error_message,
        retry_count=task.retry_count, started_at=as_utc(task.started_at), finished_at=as_utc(task.finished_at),
        created_at=as_utc(task.created_at), updated_at=as_utc(task.updated_at),
        result_available=task.status == "completed" and bool(task.result_path),
    )


@router.get("", response_model=Page[TaskOut], dependencies=[Depends(require_admin)])
async def list_tasks(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     status: str | None = None, task_type: str | None = None, telegram_chat_id: str | None = None) -> Page[TaskOut]:
    stmt = select(SyncTask)
    if status:
        stmt = stmt.where(SyncTask.status == status)
    if task_type:
        stmt = stmt.where(SyncTask.task_type == task_type)
    if telegram_chat_id:
        chat_id = parse_telegram_id(telegram_chat_id)
        stmt = stmt.join(Channel, Channel.id == SyncTask.channel_id).where(Channel.telegram_chat_id == chat_id)
    async with request.app.state.db.sessions() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (await session.scalars(stmt.order_by(SyncTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return Page(items=[await task_out(request, row) for row in rows], total=total, page=page, page_size=page_size)


@router.get("/{task_id}", response_model=TaskOut, dependencies=[Depends(require_admin)])
async def get_task(task_id: str, request: Request) -> TaskOut:
    return await task_out(request, await request.app.state.tasks.get(task_id))


@router.post("/{task_id}/retry", response_model=TaskOut, status_code=202, dependencies=[Depends(require_csrf)])
async def retry(task_id: str, request: Request) -> TaskOut:
    return await task_out(request, await request.app.state.tasks.retry(task_id))


@router.post("/{task_id}/cancel", response_model=TaskOut, dependencies=[Depends(require_csrf)])
async def cancel(task_id: str, request: Request) -> TaskOut:
    return await task_out(request, await request.app.state.tasks.action(task_id, "cancel"))


@router.post("/{task_id}/pause", response_model=TaskOut, dependencies=[Depends(require_csrf)])
async def pause(task_id: str, request: Request) -> TaskOut:
    return await task_out(request, await request.app.state.tasks.action(task_id, "pause"))


@router.post("/{task_id}/resume", response_model=TaskOut, dependencies=[Depends(require_csrf)])
async def resume(task_id: str, request: Request) -> TaskOut:
    return await task_out(request, await request.app.state.tasks.action(task_id, "resume"))

