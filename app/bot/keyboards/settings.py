from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.common import MenuCallback
from app.bot.callbacks.settings import SettingsCallback
from app.core.enums import EventType
from app.models.notification_settings import UserNotificationSettings


def notification_settings_keyboard(
    settings: UserNotificationSettings,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = {
        EventType.SMOKE: settings.smoke_enabled,
        EventType.LUNCH: settings.lunch_enabled,
        EventType.CUSTOM: settings.custom_enabled,
    }
    for event_type, enabled in fields.items():
        builder.button(
            text=f"{event_type.emoji} {event_type.default_title} {'✅' if enabled else '❌'}",
            callback_data=SettingsCallback(action=event_type.value),
        )
    builder.button(
        text="🔕 Выключить всё" if settings.notifications_enabled else "🔔 Включить всё",
        callback_data=SettingsCallback(action="all"),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data=MenuCallback(action="menu").pack(),
        )
    )
    builder.adjust(1)
    return builder.as_markup()
