from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services.event_service import EventService
from app.services.event_view_service import EventViewService
from app.services.invitation_service import InvitationService
from app.services.notification_service import AsyncRateLimiter, NotificationService
from app.services.party_service import PartyService
from app.services.stats_service import StatsService
from app.services.user_service import UserService


@dataclass(slots=True)
class RequestServices:
    users: UserService
    parties: PartyService
    events: EventService
    stats: StatsService


class ServiceContainer:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        bot: Bot,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.bot = bot
        self.invitations = InvitationService()
        telegram_rate_limiter = AsyncRateLimiter(settings.notification_rate_per_second)
        self.notifications = NotificationService(
            session_factory,
            bot,
            settings,
            rate_limiter=telegram_rate_limiter,
        )
        self.event_views = EventViewService(
            session_factory,
            bot,
            settings,
            rate_limiter=telegram_rate_limiter,
        )

    def for_session(self, session: AsyncSession) -> RequestServices:
        return RequestServices(
            users=UserService(session, self.settings.default_timezone),
            parties=PartyService(session, self.invitations),
            events=EventService(session, self.settings),
            stats=StatsService(session),
        )
