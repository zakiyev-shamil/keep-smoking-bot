from aiogram import Router

from app.bot.handlers import common, errors, event, party, settings


def build_router() -> Router:
    router = Router(name="office-party")
    router.include_router(common.router)
    router.include_router(party.router)
    router.include_router(event.router)
    router.include_router(settings.router)
    router.errors.register(errors.global_error_handler)
    return router
