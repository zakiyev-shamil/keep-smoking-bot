from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from structlog.stdlib import get_logger

from app.services.container import ServiceContainer

logger = get_logger(__name__)


class FastCallbackAnswerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                logger.warning("callback_answer_failed", callback_id=event.id)
        return await handler(event, data)


class ServicesMiddleware(BaseMiddleware):
    def __init__(self, container: ServiceContainer) -> None:
        self.container = container

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = event.from_user if isinstance(event, (Message, CallbackQuery)) else None
        if telegram_user is None or telegram_user.is_bot:
            return await handler(event, data)
        update = data.get("event_update")
        update_id = getattr(update, "update_id", None)
        fields: dict[str, Any] = {
            "update_id": update_id,
            "telegram_user_id": telegram_user.id,
            "update_kind": "callback" if isinstance(event, CallbackQuery) else "message",
        }
        if isinstance(event, CallbackQuery):
            callback_parts = (event.data or "").split(":")
            fields["callback_prefix"] = callback_parts[0] if callback_parts else None
            fields["callback_action"] = callback_parts[1] if len(callback_parts) > 1 else None
        elif isinstance(event, Message):
            fields["content_type"] = event.content_type
            if event.text and event.text.startswith("/"):
                fields["command"] = event.text.split(maxsplit=1)[0]
        logger.info("telegram_update_received", **fields)
        started_at = monotonic()
        async with self.container.session_factory() as session:
            services = self.container.for_session(session)
            current_user = await services.users.ensure_from_telegram(telegram_user)
            data["services"] = services
            data["current_user"] = current_user
            data["container"] = self.container
            try:
                result = await handler(event, data)
                logger.info(
                    "telegram_update_completed",
                    **fields,
                    duration_ms=round((monotonic() - started_at) * 1000, 2),
                )
                return result
            except Exception:
                await session.rollback()
                logger.exception(
                    "telegram_update_failed",
                    **fields,
                    duration_ms=round((monotonic() - started_at) * 1000, 2),
                )
                raise
