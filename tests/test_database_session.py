from app.database.session import create_engine


async def test_serverless_engine_uses_small_reusable_pool():
    engine = create_engine(
        "postgresql+asyncpg://user:password@localhost/database",
        serverless=True,
    )
    pool = engine.pool
    try:
        assert pool.size() == 3
        assert pool._max_overflow == 2
        assert pool._timeout == 5
        assert pool._recycle == 240
    finally:
        await engine.dispose()
