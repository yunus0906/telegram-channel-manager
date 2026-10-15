from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_proxy_url: str | None = None
    admin_password_hash: str = ""
    session_secret: str = ""
    database_url: str | None = None
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

    @property
    def telegram_proxy(self) -> tuple[str, str, int] | None:
        if not self.tg_proxy_url:
            return None
        parsed = urlsplit(self.tg_proxy_url)
        assert parsed.hostname is not None and parsed.port is not None
        return parsed.scheme, parsed.hostname, parsed.port

    @property
    def sqlite_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.data_root / 'manager.sqlite3').as_posix()}"

    @property
    def allowed_origins(self) -> set[str]:
        return {origin.strip() for origin in self.cors_origins.split(",") if origin.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

