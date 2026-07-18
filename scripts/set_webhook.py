from __future__ import annotations

import asyncio
import os

from aiogram import Bot

from app.core.config import get_settings


async def run() -> None:
    settings = get_settings()
    base_url = os.environ.get("WEBHOOK_BASE_URL", "").strip().rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("WEBHOOK_BASE_URL must be an https:// Vercel deployment URL")
    secret = settings.webhook_secret.get_secret_value()
    if not secret:
        raise RuntimeError("WEBHOOK_SECRET is required")

    bot = Bot(settings.bot_token.get_secret_value())
    try:
        await bot.set_webhook(
            url=f"{base_url}/api/telegram",
            secret_token=secret,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
        )
        info = await bot.get_webhook_info()
        print(f"Webhook configured: {info.url}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
