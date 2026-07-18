from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    EventType,
    NotificationStatus,
    PartyRole,
    ResponseType,
)
from app.core.time import utc_now
from app.models.event import Event
from app.models.event_response import EventResponse
from app.models.notification import Notification
from app.models.notification_settings import UserNotificationSettings
from app.models.party_member import PartyMember
from app.models.user import User

EVENT_SETTING_COLUMNS = {
    EventType.SMOKE: UserNotificationSettings.smoke_enabled,
    EventType.COFFEE: UserNotificationSettings.coffee_enabled,
    EventType.LUNCH: UserNotificationSettings.lunch_enabled,
    EventType.AFTER_WORK: UserNotificationSettings.after_work_enabled,
    EventType.CUSTOM: UserNotificationSettings.custom_enabled,
}


@dataclass(slots=True, frozen=True)
class NotificationMessageTarget:
    user_id: UUID
    telegram_user_id: int
    message_id: int
    response: ResponseType | None
    role: PartyRole


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def eligible_users(
        self, *, party_id: UUID, creator_id: UUID, event_type: EventType
    ) -> list[tuple[User, UserNotificationSettings | None]]:
        type_enabled = EVENT_SETTING_COLUMNS[event_type]
        rows = (
            await self.session.execute(
                select(User, UserNotificationSettings)
                .join(
                    PartyMember,
                    (PartyMember.user_id == User.id)
                    & (PartyMember.party_id == party_id)
                    & PartyMember.is_active.is_(True),
                )
                .outerjoin(
                    UserNotificationSettings,
                    UserNotificationSettings.user_id == User.id,
                )
                .where(
                    User.id != creator_id,
                    User.is_active.is_(True),
                    User.bot_accessible.is_(True),
                    or_(
                        UserNotificationSettings.user_id.is_(None),
                        (
                            UserNotificationSettings.notifications_enabled.is_(True)
                            & type_enabled.is_(True)
                        ),
                    ),
                )
                .order_by(User.id)
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    async def party_candidates(
        self, party_id: UUID
    ) -> list[tuple[User, UserNotificationSettings | None]]:
        rows = (
            await self.session.execute(
                select(User, UserNotificationSettings)
                .join(
                    PartyMember,
                    (PartyMember.user_id == User.id)
                    & (PartyMember.party_id == party_id)
                    & PartyMember.is_active.is_(True),
                )
                .outerjoin(
                    UserNotificationSettings,
                    UserNotificationSettings.user_id == User.id,
                )
                .order_by(User.id)
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    async def users_by_ids(
        self, user_ids: Sequence[UUID]
    ) -> list[tuple[User, UserNotificationSettings | None]]:
        if not user_ids:
            return []
        rows = (
            await self.session.execute(
                select(User, UserNotificationSettings)
                .outerjoin(
                    UserNotificationSettings,
                    UserNotificationSettings.user_id == User.id,
                )
                .where(
                    User.id.in_(user_ids),
                    User.is_active.is_(True),
                    User.bot_accessible.is_(True),
                )
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    async def seed(self, event_id: UUID, recipient_ids: Sequence[UUID]) -> None:
        if not recipient_ids:
            return
        values = [
            {
                "event_id": event_id,
                "recipient_id": recipient_id,
                "status": NotificationStatus.PENDING,
            }
            for recipient_id in recipient_ids
        ]
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            statement = postgresql_insert(Notification).values(values)
            await self.session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[Notification.event_id, Notification.recipient_id]
                )
            )
        elif bind.dialect.name == "sqlite":
            statement = sqlite_insert(Notification).values(values)
            await self.session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[Notification.event_id, Notification.recipient_id]
                )
            )
        else:
            for item in values:
                exists = await self.session.scalar(
                    select(Notification.id).where(
                        Notification.event_id == event_id,
                        Notification.recipient_id == item["recipient_id"],
                    )
                )
                if exists is None:
                    self.session.add(Notification(**item))

    async def pending_recipient_ids(self, event_id: UUID) -> list[UUID]:
        result = await self.session.scalars(
            select(Notification.recipient_id).where(
                Notification.event_id == event_id,
                Notification.status == NotificationStatus.PENDING,
            )
        )
        return list(result)

    async def claim_recipients(
        self,
        event_id: UUID,
        recipient_ids: Sequence[UUID],
        *,
        lease_minutes: int = 5,
    ) -> list[UUID]:
        if not recipient_ids:
            return []
        stale_before = utc_now() - timedelta(minutes=lease_minutes)
        result = await self.session.scalars(
            update(Notification)
            .where(
                Notification.event_id == event_id,
                Notification.recipient_id.in_(recipient_ids),
                or_(
                    Notification.status == NotificationStatus.PENDING,
                    (
                        (Notification.status == NotificationStatus.SENDING)
                        & (Notification.updated_at <= stale_before)
                    ),
                ),
            )
            .values(
                status=NotificationStatus.SENDING,
                error_code=None,
                updated_at=func.now(),
            )
            .returning(Notification.recipient_id)
        )
        return list(result)

    async def pending_event_ids(self, limit: int = 100) -> list[UUID]:
        result = await self.session.scalars(
            select(Notification.event_id)
            .where(
                Notification.status.in_([NotificationStatus.PENDING, NotificationStatus.SENDING])
            )
            .distinct()
            .limit(limit)
        )
        return list(result)

    async def mark(
        self,
        *,
        event_id: UUID,
        recipient_id: UUID,
        status: NotificationStatus,
        telegram_message_id: int | None = None,
        error_code: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.event_id == event_id,
                Notification.recipient_id == recipient_id,
            )
            .values(
                status=status,
                telegram_message_id=telegram_message_id,
                error_code=error_code,
                sent_at=sent_at,
                updated_at=func.now(),
            )
        )

    async def sent_message_targets(self, event_id: UUID) -> list[NotificationMessageTarget]:
        rows = (
            await self.session.execute(
                select(
                    User.id,
                    User.telegram_user_id,
                    Notification.telegram_message_id,
                    EventResponse.response,
                    PartyMember.role,
                )
                .join(
                    Notification,
                    (Notification.recipient_id == User.id) & (Notification.event_id == event_id),
                )
                .join(Event, Event.id == Notification.event_id)
                .join(
                    PartyMember,
                    (PartyMember.user_id == User.id)
                    & (PartyMember.party_id == Event.party_id)
                    & PartyMember.is_active.is_(True),
                )
                .outerjoin(
                    EventResponse,
                    (EventResponse.event_id == event_id) & (EventResponse.user_id == User.id),
                )
                .where(
                    Notification.status == NotificationStatus.SENT,
                    Notification.telegram_message_id.is_not(None),
                )
                .order_by(User.id)
            )
        ).all()
        return [
            NotificationMessageTarget(
                user_id=user_id,
                telegram_user_id=telegram_user_id,
                message_id=message_id,
                response=response,
                role=role,
            )
            for user_id, telegram_user_id, message_id, response, role in rows
            if message_id is not None
        ]
