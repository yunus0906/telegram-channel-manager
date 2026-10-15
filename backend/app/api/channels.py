from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import delete, func, or_, select

from app.api.deps import managed_channel, parse_telegram_id, require_admin, require_csrf
from app.core.errors import AppError
from app.db.models import Channel, MediaFile, Message, SyncTask, as_utc, utcnow
from app.schemas.api import ActionResult, AvailableChannel, ChannelCreate, ChannelOut, ChannelStats, Page, PurgeConfirm, TaskOut


router = APIRouter(prefix="/channels", tags=["channels"])


async def channel_out(request: Request, channel: Channel) -> ChannelOut:
    async with request.app.state.db.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(Message).where(Message.channel_id == channel.id)) or 0
    return ChannelOut(
        telegram_chat_id=str(channel.telegram_chat_id), title=channel.title, username=channel.username,
        access_type=channel.access_type, permalink=f"https://t.me/{channel.username}" if channel.username else None,
        is_managed=channel.is_managed, history_sync_enabled=channel.history_sync_enabled,
        live_listener_enabled=channel.live_listener_enabled, message_count=count,
        last_history_sync_at=as_utc(channel.last_history_sync_at),
        last_message_id=str(channel.last_message_id) if channel.last_message_id is not None else None,
        last_error=channel.last_error, created_at=as_utc(channel.created_at), updated_at=as_utc(channel.updated_at),
    )


@router.get("", response_model=Page[ChannelOut], dependencies=[Depends(require_admin)])
async def list_channels(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                        q: str = Query("", max_length=100), access_type: str | None = None) -> Page[ChannelOut]:
    stmt = select(Channel).where(Channel.is_managed.is_(True))
    if q:
        stmt = stmt.where(Channel.title.ilike(f"%{q.replace('%', r'\%').replace('_', r'\_')}%", escape="\\"))
    if access_type in {"public", "private"}:
        stmt = stmt.where(Channel.access_type == access_type)
    async with request.app.state.db.sessions() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        channels = (await session.scalars(stmt.order_by(Channel.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return Page(items=[await channel_out(request, item) for item in channels], total=total, page=page, page_size=page_size)


@router.get("/available", response_model=list[AvailableChannel], dependencies=[Depends(require_admin)])
async def available(request: Request) -> list[AvailableChannel]:
    return await request.app.state.telegram.discover()


@router.post("", response_model=list[ChannelOut], status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def add_channels(data: ChannelCreate, request: Request) -> list[ChannelOut]:
    requested = [parse_telegram_id(value) for value in data.telegram_chat_ids]
    if len(set(requested)) != len(requested):
        raise AppError(422, "duplicate_channel", "频道列表中存在重复 ID")
    discovered = {int(item.telegram_chat_id): item for item in await request.app.state.telegram.discover()}
    if any(chat_id not in discovered for chat_id in requested):
        raise AppError(403, "channel_inaccessible", "当前账号无法访问某个频道")
    rows: list[Channel] = []
    async with request.app.state.db.sessions() as session:
        async with session.begin():
            for chat_id in requested:
                info = discovered[chat_id]
                row = await session.scalar(select(Channel).where(Channel.telegram_chat_id == chat_id))
                if row is None:
                    row = Channel(telegram_chat_id=chat_id, title=info.title, username=info.username, access_type=info.access_type)
                    session.add(row)
                else:
                    row.title = info.title
                    row.username = info.username
                    row.access_type = info.access_type
                    row.is_managed = True
                    row.updated_at = utcnow()
                rows.append(row)
        for row in rows:
            await session.refresh(row)
    for row in rows:
        await request.app.state.hub.publish({"event_id": f"channel-{row.id}-{row.updated_at.timestamp()}",
                                             "type": "channel.updated", "channel_id": str(row.telegram_chat_id),
                                             "message_id": None, "timestamp": row.updated_at.isoformat(), "data": {}})
    return [await channel_out(request, row) for row in rows]


@router.get("/{channel_id}", response_model=ChannelOut, dependencies=[Depends(require_admin)])
async def get_channel(channel_id: str, request: Request) -> ChannelOut:
    return await channel_out(request, await managed_channel(request, channel_id))


@router.delete("/{channel_id}", response_model=ActionResult, dependencies=[Depends(require_csrf)])
async def remove_channel(channel_id: str, request: Request) -> ActionResult:
    channel = await managed_channel(request, channel_id)
    async with request.app.state.db.sessions() as session:
        row = await session.get(Channel, channel.id)
        row.is_managed = False
        row.live_listener_enabled = False
        row.history_sync_enabled = False
        await session.commit()
    return ActionResult()


@router.post("/{channel_id}/purge", response_model=ActionResult, dependencies=[Depends(require_csrf)])
async def purge_channel(channel_id: str, data: PurgeConfirm, request: Request) -> ActionResult:
    channel = await managed_channel(request, channel_id)
    if data.confirm_telegram_chat_id != str(channel.telegram_chat_id):
        raise AppError(422, "confirmation_mismatch", "请输入完整的 Telegram Chat ID 确认删除")
    async with request.app.state.db.sessions() as session:
        active = await session.scalar(select(func.count()).select_from(SyncTask).where(
            or_(SyncTask.channel_id == channel.id,
                (SyncTask.channel_id.is_(None) & SyncTask.task_type.in_(("json_export", "jsonl_export", "zip_export")))),
            SyncTask.status.in_(("pending", "running", "paused"))))
        if active:
            raise AppError(409, "active_tasks", "请先取消该频道的活动任务")
        media_paths = (await session.scalars(select(MediaFile.relative_path).where(MediaFile.channel_id == channel.id))).all()
        export_tasks = (await session.scalars(select(SyncTask).where(SyncTask.result_path.is_not(None)))).all()
    from app.core.paths import within_root
    for relative in media_paths:
        if relative:
            within_root(request.app.state.settings.data_root, relative).unlink(missing_ok=True)
    for task in export_tasks:
        path = within_root(request.app.state.settings.data_root, task.result_path)
        path.unlink(missing_ok=True)
        if path.suffix == ".zip":
            path.with_suffix(".json").unlink(missing_ok=True)
    for path in request.app.state.settings.data_root.rglob(f"events-{channel.telegram_chat_id}.jsonl"):
        if path.resolve().is_relative_to(request.app.state.settings.data_root.resolve()):
            path.unlink(missing_ok=True)
    export_root = await request.app.state.exports.root()
    for path in export_root.iterdir():
        if path.is_file() and path.suffix in {".json", ".jsonl", ".zip"}:
            path.unlink(missing_ok=True)
    async with request.app.state.db.sessions() as session:
        for task in (await session.scalars(select(SyncTask).where(SyncTask.result_path.is_not(None)))).all():
            task.result_path = None
            task.status = "failed"
            task.error_message = "本地频道数据已删除，导出文件失效"
        await session.execute(delete(SyncTask).where(SyncTask.channel_id == channel.id))
        row = await session.get(Channel, channel.id)
        await session.delete(row)
        await session.commit()
    return ActionResult()


async def create_sync(channel_id: str, request: Request, kind: str) -> TaskOut:
    channel = await managed_channel(request, channel_id)
    await request.app.state.telegram.resolve_accessible(channel.telegram_chat_id)
    if not (await request.app.state.app_settings.get()).values.history_sync_enabled:
        raise AppError(409, "sync_disabled", "历史同步已关闭")
    async with request.app.state.db.sessions() as session:
        row = await session.get(Channel, channel.id)
        row.history_sync_enabled = True
        await session.commit()
    task, _ = await request.app.state.tasks.create(kind, channel.id)
    from app.api.tasks import task_out
    return await task_out(request, task)


@router.post("/{channel_id}/sync", response_model=TaskOut, status_code=202, dependencies=[Depends(require_csrf)])
async def sync(channel_id: str, request: Request) -> TaskOut:
    return await create_sync(channel_id, request, "history")


@router.post("/{channel_id}/reconcile", response_model=TaskOut, status_code=202, dependencies=[Depends(require_csrf)])
async def reconcile(channel_id: str, request: Request) -> TaskOut:
    return await create_sync(channel_id, request, "reconcile")


@router.post("/{channel_id}/listen", response_model=ChannelOut, dependencies=[Depends(require_csrf)])
async def start_listen(channel_id: str, request: Request) -> ChannelOut:
    channel = await managed_channel(request, channel_id)
    await request.app.state.telegram.resolve_accessible(channel.telegram_chat_id)
    async with request.app.state.db.sessions() as session:
        row = await session.get(Channel, channel.id)
        row.live_listener_enabled = True
        await session.commit()
        return await channel_out(request, row)


@router.delete("/{channel_id}/listen", response_model=ChannelOut, dependencies=[Depends(require_csrf)])
async def stop_listen(channel_id: str, request: Request) -> ChannelOut:
    channel = await managed_channel(request, channel_id)
    async with request.app.state.db.sessions() as session:
        row = await session.get(Channel, channel.id)
        row.live_listener_enabled = False
        await session.commit()
        return await channel_out(request, row)


@router.get("/{channel_id}/stats", response_model=ChannelStats, dependencies=[Depends(require_admin)])
async def stats(channel_id: str, request: Request) -> ChannelStats:
    channel = await managed_channel(request, channel_id)
    async with request.app.state.db.sessions() as session:
        message_count = await session.scalar(select(func.count()).select_from(Message).where(Message.channel_id == channel.id)) or 0
        task_count = await session.scalar(select(func.count()).select_from(SyncTask).where(SyncTask.channel_id == channel.id)) or 0
        last_date = await session.scalar(select(func.max(Message.message_date)).where(Message.channel_id == channel.id))
    return ChannelStats(telegram_chat_id=str(channel.telegram_chat_id), message_count=message_count,
                        task_count=task_count, last_message_date=as_utc(last_date))
