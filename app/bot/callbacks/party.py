from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class PartyCallback(CallbackData, prefix="pty"):
    action: str
    party_id: UUID


class PartyMembersCallback(CallbackData, prefix="pm"):
    party_id: UUID
    page: int


class PartyMemberAdminCallback(CallbackData, prefix="pma"):
    action: str
    membership_id: UUID
