from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    database_url: str,
    *,
    echo: bool = False,
    serverless: bool = False,
) -> AsyncEngine:
    options: dict[str, object] = {"echo": echo}
    if serverless and make_url(database_url).get_backend_name() == "postgresql":
        options.update(
            pool_size=3,
            max_overflow=2,
            pool_timeout=5,
            pool_recycle=240,
        )
    else:
        options["pool_pre_ping"] = True
    return create_async_engine(database_url, **options)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
