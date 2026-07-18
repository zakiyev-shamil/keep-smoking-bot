from __future__ import annotations

import asyncio

from aiogram import Bot
from structlog.stdlib import get_logger

from app.bot.dispatcher import build_dispatcher
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.fsm_storage import PostgresStorage
from app.database.session import create_engine, create_session_factory
from app.services.container import ServiceContainer
from app.workers.expiration import expiration_loop
from app.workers.notifications import NotificationWorker

logger = get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    token = settings.bot_token.get_secret_value()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = Bot(token=token)
    me = await bot.get_me()
    if not settings.bot_username:
        settings.bot_username = me.username

    container = ServiceContainer(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
    )
    notification_worker = NotificationWorker(container.notifications, container.event_views)
    notification_worker.start()
    expiration_stop = asyncio.Event()
    expiration_task = asyncio.create_task(
        expiration_loop(
            session_factory=session_factory,
            settings=settings,
            stop_event=expiration_stop,
        ),
        name="event-expiration-worker",
    )

    dispatcher = build_dispatcher(
        container=container,
        storage=PostgresStorage(session_factory),
    )

    logger.info("bot_started", bot_username=me.username)
    try:
        await dispatcher.start_polling(
            bot,
            container=container,
            notification_worker=notification_worker,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        expiration_stop.set()
        await expiration_task
        await notification_worker.stop()
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()
        logger.info("bot_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
