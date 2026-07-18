from uuid import uuid4

from aiogram.types import User as TelegramUser

from app.bot.keyboards.settings import notification_settings_keyboard
from app.core.enums import EventType
from app.services.user_service import UserService


async def test_start_registers_user_and_restores_bot_access(session):
    service = UserService(session, "Asia/Almaty")
    telegram_user = TelegramUser(id=42, is_bot=False, first_name="Artem")

    created = await service.ensure_from_telegram(telegram_user)
    created.bot_accessible = False
    await session.commit()
    restored = await service.ensure_from_telegram(
        TelegramUser(id=42, is_bot=False, first_name="Артём", username="artem")
    )

    assert restored.id == created.id
    assert restored.first_name == "Артём"
    assert restored.username == "artem"
    assert restored.bot_accessible is True
    assert await service.repository.get_settings(restored.id) is not None


async def test_toggle_all_updates_every_visible_event_type(session):
    service = UserService(session, "Asia/Almaty")
    user = await service.ensure_from_telegram(TelegramUser(id=43, is_bot=False, first_name="Max"))

    settings = await service.toggle_all_notifications(user.id)
    keyboard = notification_settings_keyboard(settings, uuid4())
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert settings.notifications_enabled is False
    assert settings.smoke_enabled is False
    assert settings.lunch_enabled is False
    assert settings.custom_enabled is False
    assert "🚬 Го курить ❌" in labels
    assert "🍔 Го обедать ❌" in labels
    assert "🎮 Своё событие ❌" in labels
    assert "🔔 Включить всё" in labels


async def test_enabling_one_type_after_global_off_is_unambiguous(session):
    service = UserService(session, "Asia/Almaty")
    user = await service.ensure_from_telegram(TelegramUser(id=44, is_bot=False, first_name="Dima"))
    await service.toggle_all_notifications(user.id)

    settings = await service.toggle_event_notification(user.id, EventType.LUNCH)

    assert settings.notifications_enabled is True
    assert settings.lunch_enabled is True
    assert settings.smoke_enabled is False
    assert settings.custom_enabled is False


async def test_disabling_every_visible_type_turns_master_switch_off(session):
    service = UserService(session, "Asia/Almaty")
    user = await service.ensure_from_telegram(TelegramUser(id=45, is_bot=False, first_name="Sasha"))

    await service.toggle_event_notification(user.id, EventType.SMOKE)
    await service.toggle_event_notification(user.id, EventType.LUNCH)
    settings = await service.toggle_event_notification(user.id, EventType.CUSTOM)

    assert settings.notifications_enabled is False
