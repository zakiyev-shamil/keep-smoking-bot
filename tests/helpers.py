from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.notification_settings import UserNotificationSettings
from app.models.user import User
from app.services.invitation_service import InvitationService
from app.services.party_service import PartyService


async def add_user(
    session: AsyncSession,
    telegram_user_id: int,
    first_name: str,
    *,
    bot_accessible: bool = True,
) -> User:
    user = User(
        telegram_user_id=telegram_user_id,
        first_name=first_name,
        is_active=True,
        bot_accessible=bot_accessible,
    )
    settings = UserNotificationSettings(timezone="Asia/Almaty")
    user.notification_settings = settings
    session.add(user)
    await session.commit()
    return user


async def party_with_members(session, members: int = 2):
    users = [await add_user(session, 1000 + index, f"User {index}") for index in range(members)]
    service = PartyService(session, InvitationService())
    party = await service.create_party(users[0].id, "Backend")
    for user in users[1:]:
        await service.join_party(user.id, party.invite_code)
    return party, users


def make_settings(**overrides) -> Settings:
    defaults = {
        "bot_token": "123456:TEST",
        "database_url": "sqlite+aiosqlite://",
        "smoke_cooldown_minutes": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)
