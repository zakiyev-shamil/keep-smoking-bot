from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.event import (
    CustomEventCallback,
    EventActionCallback,
    EventConfirmCallback,
)
from app.bot.callbacks.party import PartyCallback
from app.core.enums import EventType, ResponseType


def event_confirmation_keyboard(party_id: UUID, event_type: EventType) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{event_type.emoji} Да, погнали",
                    callback_data=EventConfirmCallback(
                        party_id=party_id, event_type=event_type.value
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=PartyCallback(action="open", party_id=party_id).pack(),
                )
            ],
        ]
    )


def custom_confirmation_keyboard(party_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📣 Позвать",
                    callback_data=CustomEventCallback(action="confirm", party_id=party_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=CustomEventCallback(action="edit", party_id=party_id).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=PartyCallback(action="open", party_id=party_id).pack(),
                ),
            ],
        ]
    )


def event_response_keyboard(
    event_id: UUID, selected: ResponseType | None = None
) -> InlineKeyboardMarkup:
    labels = {
        ResponseType.GOING: "✅ Ты идёшь" if selected == ResponseType.GOING else "✅ Иду",
        ResponseType.LATER: (
            "⏱ Ты через 5 мин" if selected == ResponseType.LATER else "⏱ Через 5 мин"
        ),
        ResponseType.DECLINED: "❌ Ты пас" if selected == ResponseType.DECLINED else "❌ Пас",
    }
    builder = InlineKeyboardBuilder()
    for response in ResponseType:
        builder.button(
            text=labels[response],
            callback_data=EventActionCallback(action=response.value, event_id=event_id),
        )
    builder.button(
        text="👀 Посмотреть участников",
        callback_data=EventActionCallback(action="view", event_id=event_id),
    )
    builder.adjust(3, 1)
    return builder.as_markup()


def event_details_keyboard(
    *,
    event_id: UUID,
    party_id: UUID,
    selected: ResponseType | None,
    is_active: bool,
    can_respond: bool,
    can_start: bool,
    can_cancel: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_active and can_respond:
        for response, label in (
            (ResponseType.GOING, "✅ Иду"),
            (ResponseType.LATER, "⏱ Через 5 минут"),
            (ResponseType.DECLINED, "❌ Пас"),
        ):
            if selected == response:
                label = {
                    ResponseType.GOING: "✅ Ты идёшь",
                    ResponseType.LATER: "⏱ Ты через 5 мин",
                    ResponseType.DECLINED: "❌ Ты пас",
                }[response]
            builder.button(
                text=label,
                callback_data=EventActionCallback(action=response.value, event_id=event_id),
            )
    if is_active:
        if can_start:
            builder.button(
                text="🚀 Выходим",
                callback_data=EventActionCallback(action="start", event_id=event_id),
            )
        if can_cancel:
            builder.button(
                text="❌ Отменить событие",
                callback_data=EventActionCallback(action="cancel", event_id=event_id),
            )
    builder.button(
        text="📊 Моя статистика",
        callback_data=PartyCallback(action="stats", party_id=party_id),
    )
    builder.button(
        text="⬅️ В Party",
        callback_data=PartyCallback(action="open", party_id=party_id),
    )
    builder.adjust(3, 1, 1, 1, 1)
    return builder.as_markup()


def event_summary_keyboard(event_id: UUID, party_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👀 Открыть событие",
                    callback_data=EventActionCallback(action="view", event_id=event_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В Party",
                    callback_data=PartyCallback(action="open", party_id=party_id).pack(),
                )
            ],
        ]
    )


def duplicate_event_keyboard(event_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Присоединиться",
                    callback_data=EventActionCallback(
                        action=ResponseType.GOING.value, event_id=event_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👀 Открыть событие",
                    callback_data=EventActionCallback(action="view", event_id=event_id).pack(),
                )
            ],
        ]
    )


def cancel_event_keyboard(event_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отменить",
                    callback_data=EventActionCallback(
                        action="cancel_confirm", event_id=event_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Назад",
                    callback_data=EventActionCallback(action="view", event_id=event_id).pack(),
                ),
            ]
        ]
    )
