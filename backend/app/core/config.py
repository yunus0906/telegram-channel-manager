from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_proxy_url: str | None = None
    admin_password_hash: str = ""
    session_secret: str = ""
    db_type: Literal["sqlite", "mysql"] = "sqlite"
    database_url: str | None = None
    mysql_host: str = "127.0.0.1"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_user: str = ""
    mysql_password: SecretStr = SecretStr("")
    mysql_database: str = ""
    data_root: Path = BACKEND_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    cookie_secure: bool = False
    cors_origins: str = "http://127.0.0.1:5173"
    media_max_bytes: int = Field(default=100 * 1024 * 1024, ge=1)

    @field_validator("data_root", mode="before")
    @classmethod
    def resolve_data_root(cls, value: str | Path) -> Path:
        path = Path(value)
        return (path if path.is_absolute() else BACKEND_ROOT / path).resolve()

    @field_validator("tg_proxy_url")
    @classmethod
    def validate_tg_proxy_url(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        value = value.strip()
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme in {"http", "socks4", "socks5"} and parsed.hostname
                     and parsed.port and not parsed.username and not parsed.password
                     and not parsed.path and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("TG_PROXY_URL 必须是带端口的 http://、socks4:// 或 socks5:// 地址")
        return value

    @model_validator(mode="after")
    def validate_database(self) -> "Settings":
        if self.db_type == "mysql":
            if self.database_url and self.database_url.strip():
                raise ValueError("DB_TYPE=mysql 时不能设置 DATABASE_URL")
            if not self.mysql_host.strip() or not self.mysql_user.strip() or not self.mysql_password.get_secret_value().strip() or not self.mysql_database.strip():
                raise ValueError("DB_TYPE=mysql 时必须配置 MYSQL_HOST、MYSQL_USER、MYSQL_PASSWORD 和 MYSQL_DATABASE")
        elif self.database_url and self.database_url.strip():
            if make_url(self.database_url).drivername != "sqlite+aiosqlite":
                raise ValueError("DB_TYPE=sqlite 时 DATABASE_URL 必须使用 sqlite+aiosqlite")
        return self

    @property
    def telegram_proxy(self) -> tuple[str, str, int] | None:
        if not self.tg_proxy_url:
            return None
        parsed = urlsplit(self.tg_proxy_url)
        assert parsed.hostname is not None and parsed.port is not None
        return parsed.scheme, parsed.hostname, parsed.port

    @property
    def async_database_url(self) -> URL:
        if self.db_type == "mysql":
            return URL.create(
                "mysql+aiomysql", username=self.mysql_user, password=self.mysql_password.get_secret_value(),
                host=self.mysql_host, port=self.mysql_port, database=self.mysql_database,
                query={"charset": "utf8mb4"},
            )
        if self.database_url and self.database_url.strip():
            return make_url(self.database_url)
        return URL.create("sqlite+aiosqlite", database=(self.data_root / "manager.sqlite3").as_posix())

    @property
    def allowed_origins(self) -> set[str]:
        return {origin.strip() for origin in self.cors_origins.split(",") if origin.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

