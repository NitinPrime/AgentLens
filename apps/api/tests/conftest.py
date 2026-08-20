import os

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Settings are read once, at import time, from the environment and then from the
# repo's .env file. These must land before anything imports the app so the suite
# behaves the same on a developer machine with a populated .env as it does on CI
# with none: the readiness probe opens the module-level engine directly, and the
# judge tests assert the offline heuristic is in use.
os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "REDIS_URL": "memory://",
        "ENVIRONMENT": "test",
        "OPENAI_API_KEY": "",
        "RATE_LIMIT_ENABLED": "false",
    }
)

import fakeredis.aioredis  # noqa: E402
import pytest_asyncio  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.dependencies import get_redis, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app import models as _models  # noqa: E402,F401


class _SharedSession:
    """Lets handlers that open their own session reuse the test session.

    The streaming endpoint deliberately opens and closes a short-lived session
    instead of holding a request-scoped one; this stand-in keeps that code path
    testable without closing the shared in-memory database.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    def __call__(self) -> "_SharedSession":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, fake_redis) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    async def override_get_redis():
        return fake_redis

    def override_get_session_factory():
        return _SharedSession(db_session)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_session_factory] = override_get_session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
