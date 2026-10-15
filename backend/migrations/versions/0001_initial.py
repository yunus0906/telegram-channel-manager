"""Initial schema for channels, messages, tasks, events, media and sessions.

Revision ID: 0001_initial
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255)),
        sa.Column("access_type", sa.String(20), nullable=False),
        sa.Column("is_managed", sa.Boolean(), nullable=False),
        sa.Column("history_sync_enabled", sa.Boolean(), nullable=False),
        sa.Column("live_listener_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_history_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_message_id", sa.BigInteger()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_channels_telegram_chat_id", "channels", ["telegram_chat_id"], unique=True)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edit_date", sa.DateTime(timezone=True)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("views", sa.Integer()),
        sa.Column("forwards", sa.Integer()),
        sa.Column("reply_to_message_id", sa.BigInteger()),
        sa.Column("media_type", sa.String(40)),
        sa.Column("media_path", sa.Text()),
        sa.Column("permalink", sa.Text()),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel_id", "telegram_message_id", name="uq_channel_message"),
    )
    op.create_index("ix_messages_channel_date", "messages", ["channel_id", "message_date"])

    op.create_table(
        "sync_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="SET NULL")),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("cursor_message_id", sa.BigInteger()),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("total_count", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("result_path", sa.Text()),
        sa.Column("requested_action", sa.String(20)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_status_created", "sync_tasks", ["status", "created_at"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sync_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_events_channel_created", "sync_events", ["channel_id", "created_at"])

    op.create_table(
        "media_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("relative_path", sa.Text()),
        sa.Column("mime_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("checksum", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel_id", "telegram_message_id", name="uq_media_message"),
    )

    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("admin_sessions")
    op.drop_table("media_files")
    op.drop_index("ix_events_channel_created", table_name="sync_events")
    op.drop_table("sync_events")
    op.drop_table("app_settings")
    op.drop_index("ix_tasks_status_created", table_name="sync_tasks")
    op.drop_table("sync_tasks")
    op.drop_index("ix_messages_channel_date", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_channels_telegram_chat_id", table_name="channels")
    op.drop_table("channels")
