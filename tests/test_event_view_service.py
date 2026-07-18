from app.core.enums import EventType, ResponseType
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

    await views.refresh_creator_message(event_id)

    assert len(bot.edits) == 1
    assert bot.edits[0]["chat_id"] == 123
    assert bot.edits[0]["message_id"] == 456
    assert "✅ Идут — 2" in bot.edits[0]["text"]
    labels = [button.text for row in bot.edits[0]["reply_markup"].inline_keyboard for button in row]
    assert "✅ Иду" not in labels
    assert "🚀 Выходим" in labels
