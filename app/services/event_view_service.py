from __future__ import annotations

import asyncio
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.bot.keyboards.event import event_details_keyboard
from app.bot.texts.ru import event_details_text
from app.core.config import Settings
from app.core.enums import EventStatus, PartyRole
from app.core.exceptions import DomainError
from app.repositories.events import EventRepository
from app.repositories.notifications import NotificationMessageTarget, NotificationRepository
from app.services.event_service import EventService

logger = get_logger(__name__)


class EventViewService:
    """Keeps the creator screen and delivered invitations in sync."""

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

    async def refresh_event_messages(self, event_id: UUID) -> None:
        try:
            async with self.session_factory() as session:
                event = await EventRepository(session).get(event_id)
                if event is None:
                    logger.info("event_views_not_found", event_id=str(event_id))
                    return
                details = await EventService(session, self.settings).get_event_details(
                    event_id,
                    event.creator_id,
                )
                targets = await NotificationRepository(session).sent_message_targets(event_id)
        except DomainError as exc:
            logger.warning(
                "event_views_unavailable",
                event_id=str(event_id),
                error=type(exc).__name__,
            )
            return
        except Exception:
            logger.exception("event_views_load_failed", event_id=str(event_id))
            return

        is_active = details.event.status == EventStatus.ACTIVE
        text = event_details_text(details)
        refreshed = 0
        failed = 0

        if event.creator_chat_id is not None and event.creator_message_id is not None:
            keyboard = event_details_keyboard(
                event_id=event_id,
                party_id=details.event.party_id,
                selected=details.requester_response,
                is_active=is_active,
                can_respond=False,
                can_start=is_active,
                can_cancel=is_active,
            )
            if await self._edit_message(
                event_id=event_id,
                chat_id=event.creator_chat_id,
                message_id=event.creator_message_id,
                text=text,
                keyboard=keyboard,
            ):
                refreshed += 1
            else:
                failed += 1

        for target in targets:
            keyboard = self._recipient_keyboard(
                event_id=event_id,
                party_id=details.event.party_id,
                target=target,
                is_active=is_active,
            )
            if await self._edit_message(
                event_id=event_id,
                chat_id=target.telegram_user_id,
                message_id=target.message_id,
                text=text,
                keyboard=keyboard,
            ):
                refreshed += 1
            else:
                failed += 1

        logger.info(
            "event_views_refreshed",
            event_id=str(event_id),
            targets=len(targets) + int(event.creator_chat_id is not None),
            refreshed=refreshed,
            failed=failed,
            going_count=details.stats.going_count,
            later_count=details.stats.later_count,
            declined_count=details.stats.declined_count,
        )

    @staticmethod
    def _recipient_keyboard(
        *,
        event_id: UUID,
        party_id: UUID,
        target: NotificationMessageTarget,
        is_active: bool,
    ):
        return event_details_keyboard(
            event_id=event_id,
            party_id=party_id,
            selected=target.response,
            is_active=is_active,
            can_respond=True,
            can_start=False,
            can_cancel=is_active and target.role in {PartyRole.OWNER, PartyRole.ADMIN},
        )

    async def _edit_message(
        self,
        *,
        event_id: UUID,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard,
    ) -> bool:
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return True
            logger.warning(
                "event_view_refresh_failed",
                event_id=str(event_id),
                chat_id=chat_id,
                message_id=message_id,
                error=str(exc),
            )
            return False
        except TelegramRetryAfter as exc:
            await asyncio.sleep(max(0, exc.retry_after))
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                logger.warning(
                    "event_view_refresh_retry_failed",
                    event_id=str(event_id),
                    chat_id=chat_id,
                    message_id=message_id,
                )
                return False
        except TelegramForbiddenError:
            logger.warning(
                "event_view_blocked",
                event_id=str(event_id),
                chat_id=chat_id,
            )
            return False
        return True
