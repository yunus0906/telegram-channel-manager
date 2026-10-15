import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telethon.errors import FloodWaitError

from app.core.errors import AppError
from app.db.models import Channel, SyncTask, utcnow
from app.services.export_service import ExportService
from app.services.media_service import MediaService
from app.services.message_store import MessageStore, iso
from app.services.settings_service import SettingsService
from app.services.tasks import TaskService
from app.telegram.client import TelegramManager
from app.websocket.hub import EventHub


logger = logging.getLogger(__name__)


class TaskRunner:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], telegram: TelegramManager, store: MessageStore,
                 tasks: TaskService, exports: ExportService, media: MediaService, settings: SettingsService, hub: EventHub):
        self.sessions = sessions
        self.telegram = telegram
        self.store = store
        self.tasks = tasks
        self.exports = exports
        self.media = media
        self.settings = settings
        self.hub = hub
        self._pump_task: asyncio.Task[None] | None = None
        self._active: dict[str, asyncio.Task[None]] = {}
        self._stop = asyncio.Event()
        self._last_reconcile = 0.0
        self._last_flush = 0.0
        self._last_connect_attempt = time.monotonic()

    async def start(self) -> None:
        await self.tasks.recover_running()
        self.telegram.set_handlers(self._live_message, self._live_message)
        if self.telegram.configured:
            try:
                await self.telegram.connect()
            except AppError:
                logger.warning("Telegram 启动连接失败，保留本地浏览功能")
        if (await self.settings.get()).values.startup_reconcile and (await self.telegram.status()).authorized:
            await self._schedule_reconcile()
        self._pump_task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        self._stop.set()
        if self._pump_task:
            self._pump_task.cancel()
            await asyncio.gather(self._pump_task, return_exceptions=True)
        for task in self._active.values():
            task.cancel()
        await asyncio.gather(*self._active.values(), return_exceptions=True)
        await self.telegram.disconnect()

    async def _pump(self) -> None:
        while not self._stop.is_set():
            try:
                values = (await self.settings.get()).values
                available = max(0, values.task_concurrency_limit - len(self._active))
                if available:
                    async with self.sessions() as session:
                        pending = (await session.scalars(select(SyncTask).where(SyncTask.status == "pending")
                                                         .order_by(SyncTask.created_at).limit(available))).all()
                    for task in pending:
                        if task.id not in self._active:
                            worker = asyncio.create_task(self._execute(task.id))
                            self._active[task.id] = worker
                            worker.add_done_callback(lambda _done, task_id=task.id: self._active.pop(task_id, None))
                now = time.monotonic()
                if (self.telegram.configured and not self.telegram.manual_disconnect and
                        not (self.telegram.client and self.telegram.client.is_connected()) and
                        now - self._last_connect_attempt >= 60):
                    self._last_connect_attempt = now
                    try:
                        await self.telegram.connect()
                        await self.hub.publish({"event_id": f"connection-{time.time()}", "type": "telegram.connection",
                                                "channel_id": None, "message_id": None, "timestamp": iso(utcnow()),
                                                "data": (await self.telegram.status()).model_dump()})
                        if (await self.telegram.status()).authorized:
                            await self._schedule_reconcile()
                    except AppError:
                        logger.warning("Telegram 自动重连失败")
                if now - self._last_flush >= 10:
                    await self.exports.flush_events()
                    self._last_flush = now
                if now - self._last_reconcile >= values.reconcile_interval_minutes * 60:
                    if (await self.telegram.status()).authorized:
                        await self._schedule_reconcile()
                    self._last_reconcile = now
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("后台轮询失败: %s", type(exc).__name__)
            await asyncio.sleep(1)

    async def _schedule_reconcile(self) -> None:
        async with self.sessions() as session:
            channels = (await session.scalars(select(Channel).where(Channel.is_managed.is_(True), Channel.live_listener_enabled.is_(True)))).all()
        for channel in channels:
            await self.tasks.create("reconcile", channel.id)

    async def _execute(self, task_id: str) -> None:
        async with self.sessions() as session:
            task = await session.get(SyncTask, task_id)
            if task is None or task.status != "pending":
                return
            task.status = "running"
            task.started_at = task.started_at or utcnow()
            task.updated_at = utcnow()
            await session.commit()
        await self._broadcast_task(task, "sync.started")
        try:
            if task.task_type in {"history", "reconcile"}:
                await self._run_history(task_id)
            elif task.task_type == "media":
                await self._run_media(task_id)
            else:
                await self._run_export(task_id)
            async with self.sessions() as session:
                row = await session.get(SyncTask, task_id)
                if row and row.status == "running":
                    row.status = "completed"
                    row.finished_at = utcnow()
                    row.updated_at = utcnow()
                    if row.task_type in {"history", "reconcile"} and row.channel_id:
                        channel = await session.get(Channel, row.channel_id)
                        if channel:
                            channel.last_history_sync_at = utcnow()
                            channel.last_error = None
                    await session.commit()
                    await self._broadcast_task(row, "sync.completed")
                    if row.task_type in {"history", "reconcile"} and (await self.settings.get()).values.auto_export_enabled:
                        await self.tasks.create("json_export", row.channel_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("任务失败 task=%s error=%s", task_id, type(exc).__name__)
            async with self.sessions() as session:
                row = await session.get(SyncTask, task_id)
                if row:
                    if row.task_type == "media" and row.channel_id and row.options.get("message_id"):
                        await self.media.set_status(row.channel_id, int(row.options["message_id"]), "failed")
                    row.status = "failed"
                    row.error_message = exc.message if isinstance(exc, AppError) else type(exc).__name__
                    row.finished_at = utcnow()
                    if row.channel_id:
                        channel = await session.get(Channel, row.channel_id)
                        if channel:
                            channel.last_error = row.error_message
                    await session.commit()
                    await self._broadcast_task(row, "sync.failed")

    async def _run_history(self, task_id: str) -> None:
        task = await self.tasks.get(task_id)
        if task.channel_id is None:
            raise AppError(422, "channel_required", "同步任务缺少频道")
        async with self.sessions() as session:
            channel = await session.get(Channel, task.channel_id)
            if channel is None or not channel.is_managed:
                raise AppError(404, "channel_not_found", "频道不存在")
            chat_id = channel.telegram_chat_id
        client = await self.telegram.require_authorized()
        entity = await self.telegram.entity(chat_id)
        cursor = task.cursor_message_id
        retries = 0
        while True:
            if not await self._can_continue(task_id):
                return
            batch_size = (await self.settings.get()).values.history_batch_size
            try:
                async with asyncio.timeout(60):
                    batch = [item async for item in client.iter_messages(entity, limit=batch_size, offset_id=cursor or 0)]
            except FloodWaitError as exc:
                retries += 1
                if retries > 5:
                    raise
                await self._record_retry(task_id)
                logger.warning("Telegram 限流等待 task=%s channel=%s retry=%s", task_id, chat_id, retries)
                await asyncio.sleep(max(1, exc.seconds))
                continue
            except (OSError, TimeoutError, ConnectionError) as exc:
                retries += 1
                if retries > 5:
                    raise exc
                await self._record_retry(task_id)
                await asyncio.sleep(min(60, 2 ** retries) + random.uniform(0, 1))
                client = await self.telegram.require_authorized()
                continue
            retries = 0
            if not batch:
                break
            cursor = min(item.id for item in batch)
            events = await self.store.save_batch(task.channel_id, batch, task_id=task_id, cursor=cursor)
            for event in events:
                await self.hub.publish(event)
            current = await self.tasks.get(task_id)
            await self._broadcast_task(current, "sync.progress")
            if len(batch) < batch_size:
                break
            await asyncio.sleep(0.3)

    async def _record_retry(self, task_id: str) -> None:
        async with self.sessions() as session:
            task = await session.get(SyncTask, task_id)
            if task:
                task.retry_count += 1
                task.updated_at = utcnow()
                await session.commit()

    async def _run_media(self, task_id: str) -> None:
        task = await self.tasks.get(task_id)
        if task.channel_id is None:
            raise AppError(422, "channel_required", "媒体任务缺少频道")
        async with self.sessions() as session:
            channel = await session.get(Channel, task.channel_id)
            if channel is None or not channel.is_managed:
                raise AppError(404, "channel_not_found", "频道不存在")
        await self.media.set_status(channel.id, int(task.options["message_id"]), "running")
        await self.media.download(channel, int(task.options["message_id"]))
        async with self.sessions() as session:
            row = await session.get(SyncTask, task_id)
            row.processed_count = 1
            row.total_count = 1
            await session.commit()

    async def _run_export(self, task_id: str) -> None:
        task = await self.tasks.get(task_id)
        path = await self.exports.generate(task)
        async with self.sessions() as session:
            row = await session.get(SyncTask, task_id)
            row.result_path = path.relative_to(self.exports.settings.data_root).as_posix()
            row.processed_count = 1
            row.total_count = 1
            await session.commit()
        await self._broadcast_task(task, "export.progress")

    async def _can_continue(self, task_id: str) -> bool:
        async with self.sessions() as session:
            task = await session.get(SyncTask, task_id)
            if task is None:
                return False
            if task.requested_action in {"pause", "cancel"}:
                task.status = "paused" if task.requested_action == "pause" else "cancelled"
                task.requested_action = None
                task.finished_at = utcnow() if task.status == "cancelled" else None
                await session.commit()
                return False
            return task.status == "running"

    async def _live_message(self, chat_id: int, message: Any) -> None:
        async with self.sessions() as session:
            channel = await session.scalar(select(Channel).where(Channel.telegram_chat_id == chat_id, Channel.is_managed.is_(True)))
            if channel is None or not channel.live_listener_enabled:
                return
            channel_id = channel.id
        if not (await self.settings.get()).values.realtime_enabled:
            return
        try:
            emitted = await self.store.save_batch(channel_id, [message])
            for event in emitted:
                await self.hub.publish(event)
        except Exception as exc:
            logger.error("实时消息处理失败 channel=%s error=%s", chat_id, type(exc).__name__)
            async with self.sessions() as session:
                row = await session.get(Channel, channel_id)
                if row:
                    row.last_error = type(exc).__name__
                    await session.commit()
            await self.tasks.create("reconcile", channel_id)

    async def _broadcast_task(self, task: SyncTask, kind: str) -> None:
        chat_id: str | None = None
        if task.channel_id:
            async with self.sessions() as session:
                channel = await session.get(Channel, task.channel_id)
                chat_id = str(channel.telegram_chat_id) if channel else None
        await self.hub.publish({"event_id": f"task-{task.id}-{task.updated_at.timestamp() if task.updated_at else time.time()}",
                                "type": kind, "channel_id": chat_id, "message_id": None, "timestamp": iso(utcnow()),
                                "data": {"task_id": task.id, "status": task.status, "processed_count": task.processed_count,
                                         "total_count": task.total_count}})

