from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class EventCreateCallback(CallbackData, prefix="new"):
    party_id: UUID
    event_type: str


class EventConfirmCallback(CallbackData, prefix="ec"):
    party_id: UUID
    event_type: str


class CustomEventCallback(CallbackData, prefix="custom"):
    action: str
    party_id: UUID


class EventActionCallback(CallbackData, prefix="evt"):
    action: str
    event_id: UUID
