from __future__ import annotations

from uuid import UUID


class DomainError(Exception):
    """Expected business error safe to translate into a user-facing message."""


class PartyNotFoundError(DomainError):
    pass


class NotPartyMemberError(DomainError):
    pass


class PermissionDeniedError(DomainError):
    pass


class EventNotFoundError(DomainError):
    pass


class EventAlreadyExistsError(DomainError):
    def __init__(self, event_id: UUID) -> None:
        self.event_id = event_id
        super().__init__(f"Active event already exists: {event_id}")


class EventExpiredError(DomainError):
    pass


class EventNotActiveError(DomainError):
    pass


class CooldownActiveError(DomainError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(f"Cooldown active for {self.retry_after_seconds} seconds")


class InvalidInvitationError(DomainError):
    pass


class InvalidEventTitleError(DomainError):
    pass


class InvalidPollOptionsError(DomainError):
    pass


class InvalidPollOptionError(DomainError):
    pass


class PartyNameInvalidError(DomainError):
    pass
