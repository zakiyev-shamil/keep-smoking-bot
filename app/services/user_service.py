from __future__ import annotations

from aiogram.types import User as TelegramUser
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import get_logger

from app.core.enums import EventType
from app.core.time import utc_now
from app.models.notification_settings import UserNotificationSettings
from app.models.user import User
from app.repositories.users import UserRepository

logger = get_logger(__name__)

SETTING_FIELDS = {
    EventType.SMOKE: "smoke_enabled",
    EventType.COFFEE: "coffee_enabled",
    EventType.LUNCH: "lunch_enabled",
    EventType.AFTER_WORK: "after_work_enabled",
    EventType.CUSTOM: "custom_enabled",
}
ALL_EVENT_SETTING_FIELDS = tuple(SETTING_FIELDS.values())
VISIBLE_EVENT_SETTING_FIELDS = (
    SETTING_FIELDS[EventType.SMOKE],
    SETTING_FIELDS[EventType.LUNCH],
    SETTING_FIELDS[EventType.CUSTOM],
)


class UserService:
    def __init__(self, session: AsyncSession, default_timezone: str) -> None:
        self.session = session
        self.repository = UserRepository(session)
        self.default_timezone = default_timezone

    async def ensure_from_telegram(self, telegram_user: TelegramUser) -> User:
        user = await self.repository.get_by_telegram_id(telegram_user.id)
        created = user is None
        try:
            if user is None:
                user = self.repository.add(
                    telegram_user_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name,
                    language_code=telegram_user.language_code,
                    last_activity_at=utc_now(),
                )
                await self.session.flush()
                self.repository.add_default_settings(user.id, self.default_timezone)
            else:
                await self._refresh_user(user, telegram_user)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            user = await self.repository.get_by_telegram_id(telegram_user.id)
            if user is None:
                raise
            created = False
            await self._refresh_user(user, telegram_user)
            await self.session.commit()
        if created:
            logger.info(
                "user_registered",
                user_id=str(user.id),
                telegram_user_id=user.telegram_user_id,
            )
        return user

    async def _refresh_user(self, user: User, telegram_user: TelegramUser) -> None:
        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        user.language_code = telegram_user.language_code
        user.last_activity_at = utc_now()
        user.bot_accessible = True
        user.is_active = True
        if await self.repository.get_settings(user.id) is None:
            self.repository.add_default_settings(user.id, self.default_timezone)

    async def get_settings(self, user_id) -> UserNotificationSettings:
        settings = await self.repository.get_settings(user_id)
        if settings is None:
            settings = self.repository.add_default_settings(user_id, self.default_timezone)
            await self.session.commit()
        return settings

    async def toggle_event_notification(
        self, user_id, event_type: EventType
    ) -> UserNotificationSettings:
        settings = await self.get_settings(user_id)
        field = SETTING_FIELDS[event_type]
        if not settings.notifications_enabled:
            for setting_field in ALL_EVENT_SETTING_FIELDS:
                setattr(settings, setting_field, False)
            setattr(settings, field, True)
        else:
            setattr(settings, field, not getattr(settings, field))
        settings.notifications_enabled = any(
            getattr(settings, setting_field) for setting_field in VISIBLE_EVENT_SETTING_FIELDS
        )
        await self.session.commit()
        return settings

    async def toggle_all_notifications(self, user_id) -> UserNotificationSettings:
        settings = await self.get_settings(user_id)
        target = not settings.notifications_enabled
        settings.notifications_enabled = target
        for field in ALL_EVENT_SETTING_FIELDS:
            setattr(settings, field, target)
        await self.session.commit()
        return settings
