from __future__ import annotations

from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.bot.keyboards.event import event_details_keyboard
from app.bot.texts.ru import event_details_text
from app.core.config import Settings
from app.core.enums import EventStatus
from app.core.exceptions import DomainError
from app.repositories.events import EventRepository
from app.services.event_service import EventService

logger = get_logger(__name__)


class EventViewService:
    """Keeps the creator's latest Telegram view in sync."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bot: Bot,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.bot = bot
        self.settings = settings

    async def register_creator_message(
        self,
        *,
        event_id: UUID,
        creator_id: UUID,
        chat_id: int,
        message_id: int,
    ) -> None:
        async with self.session_factory() as session:
            registered = await EventRepository(session).set_creator_view(
                event_id=event_id,
                creator_id=creator_id,
                chat_id=chat_id,
                message_id=message_id,
            )
            await session.commit()
        if not registered:
            logger.warning(
                "creator_event_view_registration_rejected",
                event_id=str(event_id),
                creator_id=str(creator_id),
            )
            return
        logger.info(
            "creator_event_view_registered",
            event_id=str(event_id),
            creator_id=str(creator_id),
            chat_id=chat_id,
            message_id=message_id,
        )

    async def refresh_creator_message(self, event_id: UUID) -> None:
        try:
            async with self.session_factory() as session:
                event = await EventRepository(session).get(event_id)
                if (
                    event is None
                    or event.creator_chat_id is None
                    or event.creator_message_id is None
                ):
                    logger.info("creator_event_view_not_registered", event_id=str(event_id))
                    return
                creator_id = event.creator_id
                chat_id = event.creator_chat_id
                message_id = event.creator_message_id
                details = await EventService(session, self.settings).get_event_details(
                    event_id,
                    creator_id,
                )
        except DomainError as exc:
            logger.warning(
                "creator_event_view_unavailable",
                event_id=str(event_id),
                error=type(exc).__name__,
            )
            return
        except Exception:
            logger.exception("creator_event_view_load_failed", event_id=str(event_id))
            return
        is_active = details.event.status == EventStatus.ACTIVE
        keyboard = event_details_keyboard(
            event_id=event_id,
            party_id=details.event.party_id,
            selected=details.requester_response,
            is_active=is_active,
            can_respond=False,
            can_start=is_active,
            can_cancel=is_active,
        )
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=event_details_text(details),
                reply_markup=keyboard,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            logger.warning(
                "creator_event_view_refresh_failed",
                event_id=str(event_id),
                error=str(exc),
            )
            return
        except TelegramForbiddenError:
            logger.warning("creator_event_view_blocked", event_id=str(event_id))
            return
        logger.info(
            "creator_event_view_refreshed",
            event_id=str(event_id),
            going_count=details.stats.going_count,
            later_count=details.stats.later_count,
            declined_count=details.stats.declined_count,
        )
