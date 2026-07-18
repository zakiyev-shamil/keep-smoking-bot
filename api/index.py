from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bot.dispatcher import build_dispatcher
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.fsm_storage import PostgresStorage
from app.database.session import create_engine, create_session_factory
from app.services.container import ServiceContainer
from app.workers.notifications import InlineNotificationWorker


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


@app.post("/api/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    runtime: WebhookRuntime = request.app.state.runtime
    expected_secret = runtime.settings.webhook_secret.get_secret_value()
    if x_telegram_bot_api_secret_token is None or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, expected_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": runtime.bot})
    await runtime.dispatcher.feed_update(
        runtime.bot,
        update,
        container=runtime.container,
        notification_worker=runtime.notification_worker,
    )
    return {"ok": True}
