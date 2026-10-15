from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.paths import safe_relative
from app.db.models import AppSetting
from app.schemas.api import AppSettingsSchema, SettingsOut


IMMEDIATE_FIELDS = ["history_sync_enabled", "realtime_enabled", "reconcile_interval_minutes", "log_level", "task_concurrency_limit"]
NEXT_TASK_FIELDS = ["history_batch_size", "media_download_enabled", "media_save_directory", "export_directory", "default_export_format", "auto_export_enabled"]
RESTART_FIELDS = ["startup_reconcile"]


class SettingsService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def get(self) -> SettingsOut:
        async with self.sessions() as session:
            rows = (await session.scalars(select(AppSetting))).all()
        values = {row.key: row.value for row in rows}
        return SettingsOut(values=AppSettingsSchema.model_validate(values), immediate_fields=IMMEDIATE_FIELDS, next_task_fields=NEXT_TASK_FIELDS, restart_fields=RESTART_FIELDS)

    async def put(self, values: AppSettingsSchema) -> SettingsOut:
        safe_relative(values.media_save_directory)
        safe_relative(values.export_directory)
        async with self.sessions() as session:
            async with session.begin():
                for key, value in values.model_dump().items():
                    row = await session.get(AppSetting, key)
                    if row is None:
                        session.add(AppSetting(key=key, value=value))
                    else:
                        row.value = value
        return SettingsOut(values=values, immediate_fields=IMMEDIATE_FIELDS, next_task_fields=NEXT_TASK_FIELDS, restart_fields=RESTART_FIELDS)

