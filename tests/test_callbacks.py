from uuid import uuid4

from app.bot.callbacks.event import (
    CustomEventCallback,
    EventActionCallback,
    EventConfirmCallback,
)
from app.bot.callbacks.party import PartyMemberAdminCallback
from app.bot.handlers import build_router
from app.bot.keyboards.party import party_keyboard


def test_critical_callback_payloads_fit_telegram_limit():
    identifier = uuid4()
    payloads = [
        EventActionCallback(action="cancel_confirm", event_id=identifier).pack(),
        EventConfirmCallback(party_id=identifier, event_type="after_work").pack(),
        CustomEventCallback(action="confirm", party_id=identifier).pack(),
        PartyMemberAdminCallback(action="promote", membership_id=identifier).pack(),
    ]

    assert all(len(payload.encode()) <= 64 for payload in payloads)


def test_global_error_handler_is_registered_on_root_router():
    router = build_router()

    assert len(router.errors.handlers) == 1


def test_primary_party_menu_contains_only_enabled_event_types():
    labels = [button.text for row in party_keyboard(uuid4()).inline_keyboard for button in row]

    assert "🚬 Го курить" in labels
    assert "🍔 Го обедать" in labels
    assert "🎮 Другой движ" in labels
    assert "☕ Го кофе" not in labels
    assert "🍺 После работы" not in labels
