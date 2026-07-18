from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.enums import EventType, ResponseType
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


async def test_new_going_participant_silently_notifies_previous_going_users(
    session,
    session_factory,
):
    party, users = await party_with_members(session, members=4)
    events = EventService(session, make_settings())
    event = await events.create_event(
        party.id,
        users[0].id,
        EventType.SMOKE,
    )
    await events.respond(event.id, users[2].id, ResponseType.GOING)
    await events.respond(event.id, users[3].id, ResponseType.LATER)
    joined = await events.respond(event.id, users[1].id, ResponseType.GOING)
    bot = AsyncMock()
    bot.send_message.return_value = SimpleNamespace(message_id=123)
    service = NotificationService(session_factory, bot, make_settings())

    result = await service.notify_participant_joined(event.id, users[1].id)

    assert joined.became_going is True
    assert result.total == 2
    assert result.sent == 2
    recipients = {call.args[0] for call in bot.send_message.await_args_list}
    assert recipients == {
        users[0].telegram_user_id,
        users[2].telegram_user_id,
    }
    for call in bot.send_message.await_args_list:
        assert call.kwargs["disable_notification"] is True
        labels = [
            button.text for row in call.kwargs["reply_markup"].inline_keyboard for button in row
        ]
        assert labels == ["👀 Открыть событие", "⬅️ В Party"]
