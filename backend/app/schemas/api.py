from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class AuthLoginIn(BaseModel):
    password: str = Field(min_length=1)


class AuthMe(BaseModel):
    authenticated: bool
    csrf_token: str


class TelegramLoginIn(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


class TelegramVerifyIn(BaseModel):
    code: str | None = Field(default=None, max_length=20)
    password: str | None = Field(default=None, max_length=256)


class TelegramStatus(BaseModel):
    connected: bool
    authorized: bool
    configured: bool
    last_error: str | None = None
    needs_password: bool = False


class AvailableChannel(BaseModel):
    telegram_chat_id: str
    title: str
    username: str | None
    access_type: Literal["public", "private"]
    channel_type: str
    permalink: str | None


class ChannelCreate(BaseModel):
    telegram_chat_ids: list[str] = Field(min_length=1, max_length=100)


class ChannelOut(BaseModel):
    telegram_chat_id: str
    title: str
    username: str | None
    access_type: str
    permalink: str | None
    is_managed: bool
    history_sync_enabled: bool
    live_listener_enabled: bool
    message_count: int
    last_history_sync_at: datetime | None
    last_message_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class PurgeConfirm(BaseModel):
    confirm_telegram_chat_id: str


class MessageOut(BaseModel):
    telegram_message_id: str
    telegram_chat_id: str
    message_date: datetime
    edit_date: datetime | None
    text: str
    permalink: str | None
    views: int | None
    forwards: int | None
    reply_to_message_id: str | None
    media_type: str | None
    media_status: str
    media_path: str | None


class TaskOut(BaseModel):
    id: str
    telegram_chat_id: str | None
    task_type: str
    status: str
    cursor_message_id: str | None
    processed_count: int
    total_count: int | None
    error_message: str | None
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    result_available: bool


class ExportCreate(BaseModel):
    telegram_chat_id: str | None = None
    format: Literal["json", "jsonl", "zip"] = "json"
    include_media: bool = False
    media_only: bool = False
    date_from: datetime | None = None
    date_to: datetime | None = None


class DashboardOut(BaseModel):
    telegram: TelegramStatus
    channel_count: int
    listening_count: int
    message_count: int
    running_task_count: int
    last_successful_sync_at: datetime | None
    recent_errors: list[TaskOut]
    recent_activity: list[dict[str, Any]]


class AppSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    history_sync_enabled: bool = True
    realtime_enabled: bool = True
    startup_reconcile: bool = True
    reconcile_interval_minutes: int = Field(default=60, ge=5, le=10080)
    history_batch_size: int = Field(default=100, ge=10, le=500)
    media_download_enabled: bool = True
    media_save_directory: str = "media"
    export_directory: str = "exports"
    default_export_format: Literal["json", "jsonl", "zip"] = "json"
    auto_export_enabled: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    task_concurrency_limit: int = Field(default=2, ge=1, le=4)


class SettingsOut(BaseModel):
    values: AppSettingsSchema
    immediate_fields: list[str]
    next_task_fields: list[str]
    restart_fields: list[str]


class ActionResult(BaseModel):
    ok: bool = True


class TelegramMe(BaseModel):
    id: str
    username: str | None
    name: str


class ChannelStats(BaseModel):
    telegram_chat_id: str
    message_count: int
    task_count: int
    last_message_date: datetime | None


class Health(BaseModel):
    status: Literal["ok"] = "ok"


