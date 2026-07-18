from app.core.enums import EventType, NotificationStatus, ResponseType
from app.models.notification import Notification
from app.services.event_service import EventService
from app.services.event_view_service import EventViewService
from tests.helpers import make_settings, party_with_members


class RecordingBot:
    def __init__(self) -> None:
        self.edits: list[dict] = []

    async def edit_message_text(self, **kwargs) -> None:
        self.edits.append(kwargs)


async def test_response_refreshes_registered_creator_view(session_factory):
    settings = make_settings(smoke_cooldown_minutes=0)
    async with session_factory() as session:
        party, users = await party_with_members(session)
        event = await EventService(session, settings).create_event(
            party.id,
            users[0].id,
            EventType.SMOKE,
        )
        event_id = event.id
        creator_id = users[0].id
        responder_id = users[1].id

    bot = RecordingBot()
    views = EventViewService(session_factory, bot, settings)
    await views.register_creator_message(
        event_id=event_id,
        creator_id=creator_id,
        chat_id=123,
        message_id=456,
    )
    async with session_factory() as session:
        await EventService(session, settings).respond(
            event_id,
            responder_id,
            ResponseType.GOING,
        )

    await views.refresh_event_messages(event_id)

    assert len(bot.edits) == 1
    assert bot.edits[0]["chat_id"] == 123
    assert bot.edits[0]["message_id"] == 456
    assert "✅ Идут — 2" in bot.edits[0]["text"]
    labels = [button.text for row in bot.edits[0]["reply_markup"].inline_keyboard for button in row]
    assert "✅ Иду" not in labels
    assert "🚀 Выходим" in labels
    assert "🔄 Обновить" not in labels
    assert "Не ответили" not in bot.edits[0]["text"]


async def test_response_refreshes_delivered_invitation(session_factory):
    settings = make_settings(smoke_cooldown_minutes=0)
    async with session_factory() as session:
        party, users = await party_with_members(session)
        event = await EventService(session, settings).create_event(
            party.id,
            users[0].id,
            EventType.SMOKE,
        )
        session.add(
            Notification(
                event_id=event.id,
                recipient_id=users[1].id,
                status=NotificationStatus.SENT,
                telegram_message_id=777,
            )
        )
        await session.commit()
        details = await EventService(session, settings).respond(
            event.id,
            users[1].id,
            ResponseType.GOING,
        )
        event_id = event.id

    bot = RecordingBot()
    views = EventViewService(session_factory, bot, settings)
    await views.refresh_event_messages(event_id)

    assert len(bot.edits) == 1
    assert bot.edits[0]["chat_id"] == users[1].telegram_user_id
    assert bot.edits[0]["message_id"] == 777
    assert "✅ Идут — 2" in bot.edits[0]["text"]
    assert "Не ответили" not in bot.edits[0]["text"]
    labels = [button.text for row in bot.edits[0]["reply_markup"].inline_keyboard for button in row]
    assert "✅ Ты идёшь" in labels
    assert "🔄 Обновить" not in labels
    assert details.became_going is True
