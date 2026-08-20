from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _engine_url() -> str:
    url = make_url(settings.database_url)
    query = {k: v for k, v in url.query.items() if k.lower() not in {"ssl", "sslmode"}}
    return url.set(query=query).render_as_string(hide_password=False)


connect_args: dict[str, object] = {}
engine_kwargs: dict[str, object] = {
    "echo": settings.debug,
}

if settings.uses_sqlite:
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
else:
    engine_kwargs["pool_pre_ping"] = True
    # Neon requires TLS. Keep it out of the URL so asyncpg never sees odd query flags.
    connect_args["ssl"] = True
    engine_kwargs["connect_args"] = connect_args

engine = create_async_engine(_engine_url(), **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    if not settings.uses_sqlite:
        return

    db_path = settings.database_url.split("///")[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
