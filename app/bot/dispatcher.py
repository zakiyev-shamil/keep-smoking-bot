from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage

from app.bot.handlers import build_router
from app.bot.middlewares.services import FastCallbackAnswerMiddleware, ServicesMiddleware
from app.services.container import ServiceContainer


def build_dispatcher(
    *,
    container: ServiceContainer,
    storage: BaseStorage,
) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    dispatcher.callback_query.outer_middleware(FastCallbackAnswerMiddleware())
    services_middleware = ServicesMiddleware(container)
    dispatcher.message.outer_middleware(services_middleware)
    dispatcher.callback_query.outer_middleware(services_middleware)
    dispatcher.include_router(build_router())
    return dispatcher
