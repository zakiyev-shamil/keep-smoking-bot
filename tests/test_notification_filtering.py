from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.enums import EventType
from app.services.event_service import EventService
from app.services.notification_service import NotificationService
from tests.helpers import make_settings, party_with_members


async def test_filters_creator_global_disabled_and_event_type_disabled(session, session_factory):
    party, users = await party_with_members(session, members=5)
    users[1].notification_settings.notifications_enabled = False
    users[2].notification_settings.smoke_enabled = False
    users[3].bot_accessible = False
    await session.commit()
    service = NotificationService(session_factory, AsyncMock(), make_settings())

    recipients = await service.get_eligible_recipients(
        party_id=party.id,
        creator_id=users[0].id,
        event_type=EventType.SMOKE,
    )

    assert [user.id for user in recipients] == [users[4].id]


async def test_broadcast_claim_prevents_duplicate_delivery(
    session,
    session_factory,
):
    party, users = await party_with_members(session, members=3)
    event = await EventService(session, make_settings()).create_event(
        party.id,
        users[0].id,
        EventType.SMOKE,
    )
    bot = AsyncMock()
    bot.send_message.return_value = SimpleNamespace(message_id=123)
    service = NotificationService(session_factory, bot, make_settings())

    first = await service.broadcast_event(event.id)
    second = await service.broadcast_event(event.id)

    assert first.sent == 2
    assert second.total == 0
    assert bot.send_message.await_count == 2
