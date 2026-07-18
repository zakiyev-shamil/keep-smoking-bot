from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.common import MenuCallback
from app.bot.callbacks.party import PartyCallback
from app.models.party import Party


def no_party_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Создать Party",
        callback_data=MenuCallback(action="create_party"),
    )
    return builder.as_markup()


def party_selector_keyboard(parties: list[Party]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for party in parties:
        builder.button(
            text=f"🏢 {party.name}",
            callback_data=PartyCallback(action="open", party_id=party.id),
        )
    builder.button(
        text="➕ Создать Party",
        callback_data=MenuCallback(action="create_party"),
    )
    builder.adjust(1)
    return builder.as_markup()


def cancel_fsm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=MenuCallback(action="cancel_fsm").pack(),
                )
            ]
        ]
    )
