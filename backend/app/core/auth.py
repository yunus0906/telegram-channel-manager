import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import AdminSession, utcnow


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AuthService:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession]):
        self.settings = settings
        self.sessions = sessions
        self.hasher = PasswordHasher()

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def login(self, password: str) -> str | None:
        if not self.settings.admin_password_hash:
            return None
        try:
            self.hasher.verify(self.settings.admin_password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return None
        token = secrets.token_urlsafe(32)
        async with self.sessions() as session:
            session.add(AdminSession(token_hash=self.token_hash(token), expires_at=utcnow() + timedelta(hours=12)))
            await session.commit()
        return token

    async def valid(self, token: str | None) -> bool:
        if not token:
            return False
        async with self.sessions() as session:
            row = await session.get(AdminSession, self.token_hash(token))
            return bool(row and _aware(row.expires_at) > utcnow())

    async def logout(self, token: str | None) -> None:
        if not token:
            return
        async with self.sessions() as session:
            row = await session.get(AdminSession, self.token_hash(token))
            if row:
                await session.delete(row)
                await session.commit()

    def csrf(self, token: str) -> str:
        return hmac.new(self.settings.session_secret.encode(), token.encode(), hashlib.sha256).hexdigest()

    def check_csrf(self, token: str, supplied: str | None) -> bool:
        return bool(supplied and hmac.compare_digest(self.csrf(token), supplied))


class RateLimiter:
    def __init__(self) -> None:
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        values = self.requests[key]
        while values and values[0] <= now - window_seconds:
            values.popleft()
        if len(values) >= limit:
            return False
        values.append(now)
        return True

