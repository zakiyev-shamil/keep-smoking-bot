from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_settings import UserNotificationSettings
from app.models.user import User
from app.models.user_runtime_state import UserRuntimeState


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )

    def add(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        language_code: str | None,
        last_activity_at: datetime,
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            last_activity_at=last_activity_at,
            bot_accessible=True,
            is_active=True,
        )
        self.session.add(user)
        return user

    def add_default_settings(self, user_id: UUID, timezone: str) -> UserNotificationSettings:
        settings = UserNotificationSettings(user_id=user_id, timezone=timezone)
        self.session.add(settings)
        return settings

    async def get_settings(self, user_id: UUID) -> UserNotificationSettings | None:
        return await self.session.get(UserNotificationSettings, user_id)

    async def get_active_party_id(self, user_id: UUID) -> UUID | None:
        return await self.session.scalar(
            select(UserRuntimeState.active_party_id).where(UserRuntimeState.user_id == user_id)
        )

    async def set_active_party_id(self, user_id: UUID, party_id: UUID) -> None:
        values = {"user_id": user_id, "active_party_id": party_id}
        dialect = self.session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(UserRuntimeState).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[UserRuntimeState.user_id],
                set_={"active_party_id": party_id, "updated_at": func.now()},
            )
            await self.session.execute(statement)
            return
        if dialect == "sqlite":
            statement = sqlite_insert(UserRuntimeState).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[UserRuntimeState.user_id],
                set_={"active_party_id": party_id, "updated_at": func.now()},
            )
            await self.session.execute(statement)
            return
        runtime_state = await self.session.get(UserRuntimeState, user_id)
        if runtime_state is None:
            self.session.add(UserRuntimeState(**values))
        else:
            runtime_state.active_party_id = party_id
