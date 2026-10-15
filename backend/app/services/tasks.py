import asyncio
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.db.models import SyncTask, utcnow


ACTIVE = ("pending", "running", "paused")
TASK_TYPES = {"history", "reconcile", "media", "json_export", "jsonl_export", "zip_export"}


class TaskService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions
        self._create_lock = asyncio.Lock()

    async def create(self, task_type: str, channel_id: int | None, options: dict[str, Any] | None = None) -> tuple[SyncTask, bool]:
        if task_type not in TASK_TYPES:
            raise AppError(422, "invalid_task_type", "不支持的任务类型")
        options = options or {}
        async with self._create_lock:
            async with self.sessions() as session:
                rows = (await session.scalars(select(SyncTask).where(
                    SyncTask.task_type == task_type, SyncTask.channel_id == channel_id, SyncTask.status.in_(ACTIVE)
                ))).all()
                for row in rows:
                    if task_type in {"history", "reconcile"} or row.options == options:
                        return row, False
                task = SyncTask(id=str(uuid.uuid4()), channel_id=channel_id, task_type=task_type, status="pending", options=options)
                session.add(task)
                await session.commit()
                return task, True

    async def get(self, task_id: str) -> SyncTask:
        async with self.sessions() as session:
            task = await session.get(SyncTask, task_id)
            if task is None:
                raise AppError(404, "task_not_found", "任务不存在")
            return task

    async def recover_running(self) -> None:
        async with self.sessions() as session:
            await session.execute(update(SyncTask).where(SyncTask.status == "running").values(status="pending", requested_action=None, updated_at=utcnow()))
            await session.commit()

    async def action(self, task_id: str, action: str) -> SyncTask:
        async with self.sessions() as session:
            task = await session.get(SyncTask, task_id)
            if task is None:
                raise AppError(404, "task_not_found", "任务不存在")
            if task.status == "running" and task.task_type not in {"history", "reconcile"} and action in {"pause", "cancel"}:
                raise AppError(409, "task_action_unsupported", "运行中的该类任务不支持暂停或取消")
            if action == "pause" and task.status in {"pending", "running"}:
                if task.status == "pending":
                    task.status = "paused"
                else:
                    task.requested_action = "pause"
            elif action == "cancel" and task.status in ACTIVE:
                if task.status in {"pending", "paused"}:
                    task.status = "cancelled"
                    task.finished_at = utcnow()
                else:
                    task.requested_action = "cancel"
            elif action == "resume" and task.status == "paused":
                task.status = "pending"
                task.requested_action = None
            else:
                raise AppError(409, "invalid_task_transition", "当前任务状态不支持该操作")
            task.updated_at = utcnow()
            await session.commit()
            return task

    async def retry(self, task_id: str) -> SyncTask:
        old = await self.get(task_id)
        if old.status != "failed":
            raise AppError(409, "invalid_task_transition", "只有失败任务可以重试")
        new, created = await self.create(old.task_type, old.channel_id, dict(old.options))
        if not created:
            return new
        async with self.sessions() as session:
            row = await session.get(SyncTask, new.id)
            row.retry_count = old.retry_count + 1
            if old.task_type in {"history", "reconcile"}:
                row.cursor_message_id = old.cursor_message_id
                row.processed_count = old.processed_count
            await session.commit()
            return row
