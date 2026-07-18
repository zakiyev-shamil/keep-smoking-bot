from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.core.config import Settings
from app.services.event_service import EventService

logger = get_logger(__name__)


async def expiration_loop(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            async with session_factory() as session:
                await EventService(session, settings).expire_due_events()
        except Exception:
            logger.exception("expiration_worker_failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.event_expiration_interval_seconds,
            )
        except TimeoutError:
            continue
