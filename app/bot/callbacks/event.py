import base64
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


class LunchPollCallback(CallbackData, prefix="lp"):
    action: str
    party_id: UUID


class PollVoteCallback(CallbackData, prefix="pv"):
    event_id: str
    option_id: str


def compact_uuid(value: UUID) -> str:
    return base64.urlsafe_b64encode(value.bytes).decode().rstrip("=")


def expand_uuid(value: str) -> UUID:
    return UUID(bytes=base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
