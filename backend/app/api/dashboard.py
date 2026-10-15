from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import require_admin
from app.api.tasks import task_out
from app.db.models import Channel, Message, SyncEvent, SyncTask, as_utc
from app.schemas.api import DashboardOut
from app.services.message_store import iso


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut, dependencies=[Depends(require_admin)])
async def dashboard(request: Request) -> DashboardOut:
    async with request.app.state.db.sessions() as session:
        channel_count = await session.scalar(select(func.count()).select_from(Channel).where(Channel.is_managed.is_(True))) or 0
        listening_count = await session.scalar(select(func.count()).select_from(Channel).where(Channel.is_managed.is_(True), Channel.live_listener_enabled.is_(True))) or 0
        message_count = await session.scalar(select(func.count()).select_from(Message).join(Channel).where(Channel.is_managed.is_(True))) or 0
        running_count = await session.scalar(select(func.count()).select_from(SyncTask).where(SyncTask.status == "running")) or 0
        last_success = await session.scalar(select(func.max(Channel.last_history_sync_at)).where(Channel.is_managed.is_(True)))
        errors = (await session.scalars(select(SyncTask).where(SyncTask.status == "failed").order_by(SyncTask.updated_at.desc()).limit(5))).all()
        events = (await session.execute(select(SyncEvent, Channel.telegram_chat_id).join(Channel).order_by(SyncEvent.id.desc()).limit(10))).all()
    return DashboardOut(
        telegram=await request.app.state.telegram.status(), channel_count=channel_count,
        listening_count=listening_count, message_count=message_count, running_task_count=running_count,
        last_successful_sync_at=as_utc(last_success), recent_errors=[await task_out(request, row) for row in errors],
        recent_activity=[{"event_id": str(row.id), "type": row.event_type, "channel_id": str(chat_id),
                          "message_id": str(row.telegram_message_id), "timestamp": iso(row.created_at)} for row, chat_id in events],
    )
