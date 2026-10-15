from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import BACKEND_ROOT, Settings


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_async_engine(settings.sqlite_url, connect_args={"timeout": 30})
        if settings.sqlite_url.startswith("sqlite"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragmas(dbapi_connection, _record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    def migrate(self) -> None:
        Path(self.settings.data_root).mkdir(parents=True, exist_ok=True)
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", self.settings.sqlite_url.replace("+aiosqlite", ""))
        command.upgrade(config, "head")

    async def close(self) -> None:
        await self.engine.dispose()

