from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    action: str
    party_id: UUID
