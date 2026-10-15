import pytest
from argon2 import PasswordHasher

from app.core.auth import AuthService, RateLimiter
from app.core.config import Settings
from app.db.models import Base
from app.db.session import Database


@pytest.mark.asyncio
async def test_admin_session_requires_correct_password_and_can_be_revoked(tmp_path):
    settings = Settings(
        data_root=tmp_path,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        admin_password_hash=PasswordHasher().hash("right password"),
        session_secret="a-long-random-test-secret",
    )
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    auth = AuthService(settings, db.sessions)
    assert await auth.login("wrong password") is None
    token = await auth.login("right password")
    assert token is not None
    assert await auth.valid(token)
    assert auth.csrf(token) != auth.csrf("another-token")
    await auth.logout(token)
    assert not await auth.valid(token)
    await db.close()


def test_rate_limiter_blocks_excess_requests():
    limiter = RateLimiter()
    assert limiter.allow("login:local", 2, 60)
    assert limiter.allow("login:local", 2, 60)
    assert not limiter.allow("login:local", 2, 60)
    assert limiter.allow("login:other", 2, 60)
