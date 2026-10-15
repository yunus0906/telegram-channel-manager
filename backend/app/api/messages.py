from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import managed_channel, parse_telegram_id, require_admin, require_csrf
from app.core.errors import AppError
from app.db.models import MediaFile, Message, as_utc
from app.schemas.api import MessageOut, Page, TaskOut


router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["messages"])


def message_out(row: Message, chat_id: int, media_status: str | None = None) -> MessageOut:
    return MessageOut(
        telegram_message_id=str(row.telegram_message_id), telegram_chat_id=str(chat_id),
        message_date=as_utc(row.message_date), edit_date=as_utc(row.edit_date), text=row.text, permalink=row.permalink,
        views=row.views, forwards=row.forwards,
        reply_to_message_id=str(row.reply_to_message_id) if row.reply_to_message_id is not None else None,
        media_type=row.media_type, media_status="downloaded" if row.media_path else media_status or ("not_downloaded" if row.media_type else "none"),
        media_path=row.media_path,
    )


async def query_messages(channel_id: str, request: Request, page: int, page_size: int, q: str,
                         date_from: datetime | None, date_to: datetime | None, media_type: str | None) -> Page[MessageOut]:
    channel = await managed_channel(request, channel_id)
    stmt = select(Message, MediaFile.status).outerjoin(
        MediaFile, (MediaFile.channel_id == Message.channel_id) &
        (MediaFile.telegram_message_id == Message.telegram_message_id)
    ).where(Message.channel_id == channel.id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Message.text.ilike(f"%{escaped}%", escape="\\"))
    if date_from:
        stmt = stmt.where(Message.message_date >= date_from)
    if date_to:
        stmt = stmt.where(Message.message_date <= date_to)
    if media_type == "text":
        stmt = stmt.where(Message.media_type.is_(None))
    elif media_type in {"photo", "video", "document", "other"}:
        stmt = stmt.where(Message.media_type == media_type)
    elif media_type:
        raise AppError(422, "invalid_media_type", "不支持的消息类型")
    async with request.app.state.db.sessions() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (await session.execute(stmt.order_by(Message.message_date.desc(), Message.telegram_message_id.desc())
                                           .offset((page - 1) * page_size).limit(page_size))).all()
    return Page(items=[message_out(row, channel.telegram_chat_id, state) for row, state in rows], total=total,
                page=page, page_size=page_size)


@router.get("", response_model=Page[MessageOut], dependencies=[Depends(require_admin)])
async def list_messages(channel_id: str, request: Request, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                        q: str = Query("", max_length=200), date_from: datetime | None = None,
                        date_to: datetime | None = None, media_type: str | None = None) -> Page[MessageOut]:
    return await query_messages(channel_id, request, page, page_size, q, date_from, date_to, media_type)


@router.get("/search", response_model=Page[MessageOut], dependencies=[Depends(require_admin)])
async def search_messages(channel_id: str, request: Request, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                          q: str = Query("", min_length=1, max_length=200), date_from: datetime | None = None,
                          date_to: datetime | None = None, media_type: str | None = None) -> Page[MessageOut]:
    return await query_messages(channel_id, request, page, page_size, q, date_from, date_to, media_type)


async def get_local_message(channel_id: str, message_id: str, request: Request) -> tuple[int, int, Message]:
    channel = await managed_channel(request, channel_id)
    telegram_message_id = parse_telegram_id(message_id, positive=True)
    async with request.app.state.db.sessions() as session:
        row = await session.scalar(select(Message).where(Message.channel_id == channel.id,
                                                         Message.telegram_message_id == telegram_message_id))
        if row is None:
            raise AppError(404, "message_not_found", "消息不存在")
        return channel.id, channel.telegram_chat_id, row


@router.get("/{message_id}", response_model=MessageOut, dependencies=[Depends(require_admin)])
async def get_message(channel_id: str, message_id: str, request: Request) -> MessageOut:
    local_id, chat_id, row = await get_local_message(channel_id, message_id, request)
    async with request.app.state.db.sessions() as session:
        state = await session.scalar(select(MediaFile.status).where(MediaFile.channel_id == local_id,
                                                                    MediaFile.telegram_message_id == row.telegram_message_id))
    return message_out(row, chat_id, state)


@router.get("/{message_id}/media", dependencies=[Depends(require_admin)])
async def get_media(channel_id: str, message_id: str, request: Request) -> FileResponse:
    local_id, _, row = await get_local_message(channel_id, message_id, request)
    path = await request.app.state.media.path(local_id, row.telegram_message_id)
    return FileResponse(path, filename=path.name, content_disposition_type="inline" if row.media_type in {"photo", "video"} else "attachment")


@router.post("/{message_id}/media/download", response_model=TaskOut, status_code=202, dependencies=[Depends(require_csrf)])
async def download_media(channel_id: str, message_id: str, request: Request) -> TaskOut:
    local_id, _, row = await get_local_message(channel_id, message_id, request)
    if not row.media_type:
        raise AppError(404, "media_not_found", "消息没有附件")
    task, created = await request.app.state.tasks.create("media", local_id, {"message_id": str(row.telegram_message_id)})
    if created:
        await request.app.state.media.set_status(local_id, row.telegram_message_id, "pending")
    from app.api.tasks import task_out
    return await task_out(request, task)

