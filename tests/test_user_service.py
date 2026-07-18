from aiogram.types import User as TelegramUser

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
