from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.core.enums import EventType, ResponseType
from app.models.event import Event
from app.models.party import Party
from app.models.party_member import PartyMember
from app.models.user import User


@dataclass(slots=True)
class EventStats:
    going_count: int
    later_count: int
    declined_count: int
    no_response_count: int
    going_users: list[User] = field(default_factory=list)
    later_users: list[User] = field(default_factory=list)
    declined_users: list[User] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class EventPollOptionDetails:
    id: UUID
    text: str
    position: int
    vote_count: int
    selected: bool


@dataclass(slots=True, frozen=True)
class EventPoll:
    options: list[EventPollOptionDetails]
    selected_option_id: UUID | None
    read_only: bool


@dataclass(slots=True)
class EventDetails:
    event: Event
    requester_membership: PartyMember
    requester_response: ResponseType | None
    stats: EventStats
    poll: EventPoll | None = None
    response_changed: bool = False
    poll_changed: bool = False
    previous_response: ResponseType | None = None
    current_response: ResponseType | None = None

    @property
    def became_going(self) -> bool:
        return (
            self.response_changed
            and self.current_response == ResponseType.GOING
            and self.previous_response != ResponseType.GOING
        )


@dataclass(slots=True)
class EventTransition:
    event: Event
    changed: bool


@dataclass(slots=True)
class NotificationBatchResult:
    total: int
    sent: int
    failed: int
    blocked: int


@dataclass(slots=True)
class UserPartyStats:
    party: Party
    participation_by_type: dict[EventType, int]
    created_count: int
