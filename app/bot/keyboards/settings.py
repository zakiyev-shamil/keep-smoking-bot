from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.party import PartyCallback
from app.bot.callbacks.settings import SettingsCallback
from app.core.enums import EventType
from app.models.notification_settings import UserNotificationSettings


def notification_settings_keyboard(
    settings: UserNotificationSettings,
    party_id: UUID,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = {
        EventType.SMOKE: settings.smoke_enabled,
        EventType.LUNCH: settings.lunch_enabled,
        EventType.CUSTOM: settings.custom_enabled,
    }
    for event_type, enabled in fields.items():
        effectively_enabled = settings.notifications_enabled and enabled
        builder.button(
            text=(
                f"{event_type.emoji} {event_type.default_title} "
                f"{'✅' if effectively_enabled else '❌'}"
            ),
            callback_data=SettingsCallback(
                action=event_type.value,
                party_id=party_id,
            ),
        )
    builder.button(
        text="🔕 Выключить всё" if settings.notifications_enabled else "🔔 Включить всё",
        callback_data=SettingsCallback(action="all", party_id=party_id),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ В Party",
            callback_data=PartyCallback(action="open", party_id=party_id).pack(),
        )
    )
    builder.adjust(1)
    return builder.as_markup()
