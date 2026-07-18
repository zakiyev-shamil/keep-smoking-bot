from __future__ import annotations

from aiogram import Router
from aiogram.types import ErrorEvent
from structlog.stdlib import get_logger

from app.bot.texts.ru import DOMAIN_MESSAGES, GENERIC_ERROR
from app.core.exceptions import CooldownActiveError, DomainError, EventAlreadyExistsError

router = Router(name="errors")
logger = get_logger(__name__)


@router.error()
async def global_error_handler(event: ErrorEvent) -> bool:
    exception = event.exception
    update = event.update
    telegram_user = (
        update.callback_query.from_user
        if update.callback_query
        else update.message.from_user
        if update.message
        else None
    )
    if isinstance(exception, DomainError):
        logger.warning(
            "domain_error",
            update_id=update.update_id,
            telegram_user_id=telegram_user.id if telegram_user else None,
            error=type(exception).__name__,
        )
    else:
        logger.error(
            "update_failed",
            update_id=update.update_id,
            telegram_user_id=telegram_user.id if telegram_user else None,
            error=type(exception).__name__,
            exc_info=(type(exception), exception, exception.__traceback__),
        )

    if isinstance(exception, CooldownActiveError):
        minutes = max(1, (exception.retry_after_seconds + 59) // 60)
        text = f"Следующее такое событие можно создать через {minutes} мин."
    elif isinstance(exception, EventAlreadyExistsError):
        text = "Такое активное событие уже создано."
    else:
        text = DOMAIN_MESSAGES.get(type(exception).__name__, GENERIC_ERROR)

    if update.callback_query:
        if update.callback_query.message:
            await update.callback_query.message.answer(text)
    elif update.message:
        await update.message.answer(text)
    return True
