from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from aiogram.types import InlineKeyboardMarkup
from hypothesis import given, settings
from hypothesis import strategies as st

from app.bot.keyboards.common import (
    cancel_fsm_keyboard,
    menu_keyboard,
    no_party_keyboard,
    party_selector_keyboard,
)
from app.bot.keyboards.event import (
    cancel_event_keyboard,
    custom_confirmation_keyboard,
    duplicate_event_keyboard,
    event_confirmation_keyboard,
    event_details_keyboard,
    event_response_keyboard,
    event_summary_keyboard,
    lunch_poll_confirmation_keyboard,
    lunch_setup_keyboard,
)
from app.bot.keyboards.party import (
    delete_party_confirmation_keyboard,
    members_keyboard,
    party_created_keyboard,
    party_keyboard,
    stats_keyboard,
)
from app.bot.keyboards.settings import notification_settings_keyboard
from app.core.enums import EventType, PartyRole, ResponseType
from app.models.notification_settings import UserNotificationSettings
from app.models.party import Party
from app.services.dto import EventPoll, EventPollOptionDetails

PARTY_ID = UUID("00000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("00000000-0000-0000-0000-000000000002")
OWNER_ID = UUID("00000000-0000-0000-0000-000000000003")


class Screen(StrEnum):
    NO_PARTY = "no_party"
    PARTY = "party"
    PARTY_SELECTOR = "party_selector"
    CREATE_PARTY_INPUT = "create_party_input"
    PARTY_CREATED = "party_created"
    EVENT_CONFIRM = "event_confirm"
    LUNCH_SETUP = "lunch_setup"
    POLL_INPUT = "poll_input"
    POLL_CONFIRM = "poll_confirm"
    CUSTOM_INPUT = "custom_input"
    CUSTOM_CONFIRM = "custom_confirm"
    DUPLICATE = "duplicate"
    INVITATION = "invitation"
    EVENT_MEMBER = "event_member"
    EVENT_CREATOR = "event_creator"
    EVENT_DONE = "event_done"
    CANCEL_CONFIRM = "cancel_confirm"
    EVENT_SUMMARY = "event_summary"
    POLL_INVITATION = "poll_invitation"
    POLL_ACTIVE = "poll_active"
    POLL_READONLY = "poll_readonly"
    MEMBERS = "members"
    SETTINGS = "settings"
    STATS = "stats"
    ERROR = "error"
    DELETE_PARTY_CONFIRM = "delete_party_confirm"


SCREEN_TEXTS = {
    Screen.NO_PARTY: "Ты пока не состоишь ни в одной Party.",
    Screen.PARTY: "🏢 Backend\n\n👥 3 участника\n\nЧто делаем?",
    Screen.PARTY_SELECTOR: "Выбери Party:",
    Screen.CREATE_PARTY_INPUT: "Введите название Party.",
    Screen.PARTY_CREATED: "🏢 Backend создана.\n\nТеперь пригласи коллег.",
    Screen.EVENT_CONFIRM: "🚬 Позвать Backend: «Го курить»?",
    Screen.LUNCH_SETUP: "🍔 Как позвать коллег на обед?",
    Screen.POLL_INPUT: "Введи 2–6 вариантов.",
    Screen.POLL_CONFIRM: "🍔 Опрос для Backend\n\n1. Плов\n2. Пицца",
    Screen.CUSTOM_INPUT: "Что за событие?\n\nНазвание — от 1 до 100 символов.",
    Screen.CUSTOM_CONFIRM: "🎮 Настолки\n\nПозвать Backend?",
    Screen.DUPLICATE: "🚬 Уже есть активное предложение.",
    Screen.INVITATION: "🚬 Го курить\n\n✅ Идут — 1\n\nИдут:\n• Артём",
    Screen.EVENT_MEMBER: "🚬 Го курить\n\n✅ Идут — 2\n\nИдут:\n• Артём\n• Максим",
    Screen.EVENT_CREATOR: "🚬 Го курить\n\n✅ Идут — 2\n\nИдут:\n• Артём\n• Максим",
    Screen.EVENT_DONE: "🚬 Го курить\n\nСтатус: Уже вышли\n\n✅ Идут — 2",
    Screen.CANCEL_CONFIRM: "Отменить событие?",
    Screen.EVENT_SUMMARY: "👋 Максим теперь идёт\n\n🚬 Го курить · Backend",
    Screen.POLL_INVITATION: "🍔 Го обедать\n\n📊 Куда идём:\n1. Плов — 1",
    Screen.POLL_ACTIVE: "🍔 Го обедать\n\n📊 Куда идём:\n1. Плов — 2",
    Screen.POLL_READONLY: "🍔 Го обедать\n\nГолосование завершено.",
    Screen.MEMBERS: "👥 Backend\n\n3 участника",
    Screen.SETTINGS: "🔔 Уведомления\n\nВыбери, какие события тебе присылать.",
    Screen.STATS: "📊 Твоя статистика · Backend",
    Screen.ERROR: "Сценарий устарел. Открой меню и попробуй ещё раз.",
    Screen.DELETE_PARTY_CONFIRM: "Удалить Party «Backend»?",
}


def _settings(
    *,
    enabled: bool = True,
    smoke: bool = True,
    lunch: bool = True,
    custom: bool = True,
) -> UserNotificationSettings:
    return UserNotificationSettings(
        user_id=uuid4(),
        notifications_enabled=enabled,
        smoke_enabled=smoke,
        lunch_enabled=lunch,
        custom_enabled=custom,
    )


def _party() -> Party:
    return Party(
        id=PARTY_ID,
        name="Backend",
        owner_id=OWNER_ID,
        invite_code="safe-token",
    )


def _poll(*, read_only: bool = False) -> EventPoll:
    options = [
        EventPollOptionDetails(
            id=UUID("00000000-0000-0000-0000-000000000010"),
            text="Плов",
            position=0,
            vote_count=2,
            selected=True,
        ),
        EventPollOptionDetails(
            id=UUID("00000000-0000-0000-0000-000000000011"),
            text="Пицца",
            position=1,
            vote_count=1,
            selected=False,
        ),
    ]
    return EventPoll(
        options=options,
        selected_option_id=options[0].id,
        read_only=read_only,
    )


def keyboard_for(screen: Screen) -> InlineKeyboardMarkup:
    if screen == Screen.NO_PARTY:
        return no_party_keyboard()
    if screen == Screen.PARTY:
        return party_keyboard(PARTY_ID, is_owner=True)
    if screen == Screen.PARTY_SELECTOR:
        return party_selector_keyboard([_party()])
    if screen in {Screen.CREATE_PARTY_INPUT, Screen.CUSTOM_INPUT, Screen.POLL_INPUT}:
        return cancel_fsm_keyboard()
    if screen == Screen.PARTY_CREATED:
        return party_created_keyboard(PARTY_ID, "https://t.me/test_bot?start=join_token")
    if screen == Screen.EVENT_CONFIRM:
        return event_confirmation_keyboard(PARTY_ID, EventType.SMOKE)
    if screen == Screen.LUNCH_SETUP:
        return lunch_setup_keyboard(PARTY_ID)
    if screen == Screen.POLL_CONFIRM:
        return lunch_poll_confirmation_keyboard(PARTY_ID)
    if screen == Screen.CUSTOM_CONFIRM:
        return custom_confirmation_keyboard(PARTY_ID)
    if screen == Screen.DUPLICATE:
        return duplicate_event_keyboard(EVENT_ID)
    if screen == Screen.INVITATION:
        return event_response_keyboard(EVENT_ID)
    if screen == Screen.POLL_INVITATION:
        return event_response_keyboard(EVENT_ID, poll=_poll())
    if screen == Screen.EVENT_MEMBER:
        return event_details_keyboard(
            event_id=EVENT_ID,
            party_id=PARTY_ID,
            selected=ResponseType.GOING,
            is_active=True,
            can_respond=True,
            can_start=False,
            can_cancel=False,
        )
    if screen == Screen.EVENT_CREATOR:
        return event_details_keyboard(
            event_id=EVENT_ID,
            party_id=PARTY_ID,
            selected=ResponseType.GOING,
            is_active=True,
            can_respond=False,
            can_start=True,
            can_cancel=True,
        )
    if screen == Screen.POLL_ACTIVE:
        return event_details_keyboard(
            event_id=EVENT_ID,
            party_id=PARTY_ID,
            selected=ResponseType.GOING,
            is_active=True,
            can_respond=True,
            can_start=False,
            can_cancel=False,
            poll=_poll(),
        )
    if screen == Screen.POLL_READONLY:
        return event_details_keyboard(
            event_id=EVENT_ID,
            party_id=PARTY_ID,
            selected=ResponseType.GOING,
            is_active=False,
            can_respond=False,
            can_start=False,
            can_cancel=False,
            poll=_poll(read_only=True),
        )
    if screen == Screen.EVENT_DONE:
        return event_details_keyboard(
            event_id=EVENT_ID,
            party_id=PARTY_ID,
            selected=ResponseType.GOING,
            is_active=False,
            can_respond=False,
            can_start=False,
            can_cancel=False,
        )
    if screen == Screen.CANCEL_CONFIRM:
        return cancel_event_keyboard(EVENT_ID)
    if screen == Screen.EVENT_SUMMARY:
        return event_summary_keyboard(EVENT_ID, PARTY_ID)
    if screen == Screen.MEMBERS:
        return members_keyboard(
            party_id=PARTY_ID,
            page=0,
            total=0,
            page_size=10,
            requester_role=PartyRole.MEMBER,
            members=[],
        )
    if screen == Screen.SETTINGS:
        return notification_settings_keyboard(_settings(), PARTY_ID)
    if screen == Screen.STATS:
        return stats_keyboard(PARTY_ID)
    if screen == Screen.DELETE_PARTY_CONFIRM:
        return delete_party_confirmation_keyboard(PARTY_ID)
    return menu_keyboard()


def callback_buttons(screen: Screen):
    return [
        button
        for row in keyboard_for(screen).inline_keyboard
        for button in row
        if button.callback_data
    ]


def next_screen(current: Screen, callback_data: str) -> Screen:
    parts = callback_data.split(":")
    prefix = parts[0]
    action = parts[1] if len(parts) > 1 else ""
    if prefix == "menu":
        return Screen.CREATE_PARTY_INPUT if action == "create_party" else Screen.PARTY
    if prefix == "new":
        if parts[-1] == EventType.CUSTOM.value:
            return Screen.CUSTOM_INPUT
        if parts[-1] == EventType.LUNCH.value:
            return Screen.LUNCH_SETUP
        return Screen.EVENT_CONFIRM
    if prefix == "ec":
        return Screen.EVENT_CREATOR
    if prefix == "custom":
        return Screen.CUSTOM_INPUT if action == "edit" else Screen.EVENT_CREATOR
    if prefix == "lp":
        return Screen.POLL_INPUT if action in {"add", "edit"} else Screen.EVENT_CREATOR
    if prefix == "pv":
        return Screen.POLL_ACTIVE
    if prefix == "evt":
        if action == "cancel":
            return Screen.CANCEL_CONFIRM
        if action in {"start", "cancel_confirm"}:
            return Screen.EVENT_DONE
        return Screen.EVENT_MEMBER
    if prefix == "pty":
        if action == "delete":
            return Screen.DELETE_PARTY_CONFIRM
        if action == "delete_confirm":
            return Screen.PARTY
        return {
            "open": Screen.PARTY,
            "switch": Screen.PARTY_SELECTOR,
            "settings": Screen.SETTINGS,
            "stats": Screen.STATS,
            "invite": Screen.PARTY_CREATED,
        }.get(action, Screen.PARTY)
    if prefix in {"pm", "pma"}:
        return Screen.MEMBERS
    if prefix == "set":
        return Screen.SETTINGS
    raise AssertionError(f"Unknown callback from {current}: {callback_data}")


def assert_visual_contract(screen: Screen) -> None:
    text = SCREEN_TEXTS[screen]
    keyboard = keyboard_for(screen)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert 0 < len(text) <= 4096
    assert buttons
    assert callback_buttons(screen)
    assert "Не ответили" not in text
    assert "Другой движ" not in text
    for button in buttons:
        assert button.text.strip()
        assert len(button.text) <= 64
        assert "Обновить" not in button.text
        if button.callback_data:
            assert len(button.callback_data.encode()) <= 64


@settings(max_examples=100, derandomize=True, deadline=None)
@given(
    start=st.sampled_from(list(Screen)),
    choices=st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=50),
)
def test_random_button_sequences_have_no_visual_dead_ends(
    start: Screen,
    choices: list[int],
) -> None:
    current = start
    for choice in choices:
        assert_visual_contract(current)
        buttons = callback_buttons(current)
        selected = buttons[choice % len(buttons)]
        current = next_screen(current, selected.callback_data)
    assert_visual_contract(current)


def test_every_screen_can_return_to_party_within_three_clicks() -> None:
    for start in Screen:
        frontier = {start}
        visited: set[Screen] = set()
        for _depth in range(4):
            if Screen.PARTY in frontier:
                break
            visited.update(frontier)
            frontier = {
                next_screen(screen, button.callback_data)
                for screen in frontier
                for button in callback_buttons(screen)
            } - visited
        assert Screen.PARTY in frontier, f"{start} has no short path back to Party"


@settings(max_examples=50, derandomize=True)
@given(
    enabled=st.booleans(),
    smoke=st.booleans(),
    lunch=st.booleans(),
    custom=st.booleans(),
)
def test_notification_keyboard_always_shows_effective_state(
    enabled: bool,
    smoke: bool,
    lunch: bool,
    custom: bool,
) -> None:
    keyboard = notification_settings_keyboard(
        _settings(enabled=enabled, smoke=smoke, lunch=lunch, custom=custom),
        PARTY_ID,
    )
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    expected = {
        "🚬": enabled and smoke,
        "🍔": enabled and lunch,
        "🎮": enabled and custom,
    }
    for emoji, is_enabled in expected.items():
        label = next(item for item in labels if item.startswith(emoji))
        assert label.endswith("✅" if is_enabled else "❌")
