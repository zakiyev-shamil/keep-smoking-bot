from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.callbacks.party import PartyCallback
from app.bot.callbacks.settings import SettingsCallback
from app.bot.keyboards.settings import notification_settings_keyboard
from app.bot.utils import edit_or_answer
from app.core.enums import EventType
from app.models.user import User
from app.services.container import RequestServices

router = Router(name="settings")


async def show_settings(
    callback: CallbackQuery,
    current_user: User,
    services: RequestServices,
    party_id,
) -> None:
    settings = await services.users.get_settings(current_user.id)
    if callback.message:
        await edit_or_answer(
            callback.message,
            "🔔 Уведомления\n\nВыбери, какие события тебе присылать.",
            notification_settings_keyboard(settings, party_id),
        )


@router.callback_query(PartyCallback.filter(F.action == "settings"))
async def settings_from_party(
    callback: CallbackQuery,
    callback_data: PartyCallback,
    current_user: User,
    services: RequestServices,
) -> None:
    await services.parties.get_party_for_member(callback_data.party_id, current_user.id)
    await show_settings(callback, current_user, services, callback_data.party_id)


@router.callback_query(SettingsCallback.filter())
async def toggle_setting(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    current_user: User,
    services: RequestServices,
) -> None:
    if callback_data.action == "all":
        await services.users.toggle_all_notifications(current_user.id)
    else:
        await services.users.toggle_event_notification(
            current_user.id, EventType(callback_data.action)
        )
    await show_settings(callback, current_user, services, callback_data.party_id)
