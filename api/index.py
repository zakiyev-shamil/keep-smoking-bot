from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.stdlib import get_logger

from app.bot.dispatcher import build_dispatcher
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.fsm_storage import PostgresStorage
from app.database.session import create_engine, create_session_factory
from app.services.container import ServiceContainer
from app.workers.notifications import InlineNotificationWorker

logger = get_logger(__name__)
_has_served_webhook = False


@dataclass(slots=True)
class WebhookRuntime:
    settings: Settings
    engine: AsyncEngine
    bot: Bot
    dispatcher: Dispatcher
    container: ServiceContainer
    notification_worker: InlineNotificationWorker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    token = settings.bot_token.get_secret_value()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")
    if not settings.webhook_secret.get_secret_value():
        raise RuntimeError("WEBHOOK_SECRET is required")

    engine = create_engine(settings.database_url, serverless=True)
    session_factory = create_session_factory(engine)
    bot = Bot(token=token)
    container = ServiceContainer(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
    )
    dispatcher = build_dispatcher(
        container=container,
        storage=PostgresStorage(session_factory),
    )
    runtime = WebhookRuntime(
        settings=settings,
        engine=engine,
        bot=bot,
        dispatcher=dispatcher,
        container=container,
        notification_worker=InlineNotificationWorker(
            container.notifications,
            container.event_views,
        ),
    )
    app.state.runtime = runtime
    try:
        yield
    finally:
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()


app = FastAPI(
    title="Office Party Telegram Bot",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/api")
@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/database")
async def database_health(request: Request) -> dict[str, str]:
    runtime: WebhookRuntime = request.app.state.runtime
    async with runtime.container.session_factory() as session:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != "20260718_03":
        raise HTTPException(status_code=503, detail="Database schema is not current")
    hostname = urlsplit(runtime.settings.database_url).hostname or ""
    if "-pooler" not in hostname.split(".", maxsplit=1)[0]:
        raise HTTPException(status_code=503, detail="Database connection is not pooled")
    logger.info("database_health_checked", schema_revision=revision, pooled=True)
    return {"status": "ok", "database": "ok", "pooling": "pooled"}


@app.post("/api/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    global _has_served_webhook
    invocation_started_at = monotonic()
    temperature = "warm" if _has_served_webhook else "cold"
    _has_served_webhook = True
    runtime: WebhookRuntime = request.app.state.runtime
    expected_secret = runtime.settings.webhook_secret.get_secret_value()
    if x_telegram_bot_api_secret_token is None or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": runtime.bot})
    logger.info(
        "vercel_invocation_started",
        temperature=temperature,
        update_id=update.update_id,
    )
    await runtime.dispatcher.feed_update(
        runtime.bot,
        update,
        container=runtime.container,
        notification_worker=runtime.notification_worker,
    )
    logger.info(
        "vercel_invocation_completed",
        temperature=temperature,
        update_id=update.update_id,
        duration_ms=round((monotonic() - invocation_started_at) * 1000, 2),
    )
    return {"ok": True}
