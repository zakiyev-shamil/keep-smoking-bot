from __future__ import annotations

import math
import re
from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import get_logger

from app.core.config import Settings
from app.core.enums import (
    EventCreationPolicy,
    EventStatus,
    EventType,
    PartyRole,
    ResponseType,
)
from app.core.exceptions import (
    CooldownActiveError,
    EventAlreadyExistsError,
    EventExpiredError,
    EventNotActiveError,
    EventNotFoundError,
    InvalidEventTitleError,
    NotPartyMemberError,
    PartyNotFoundError,
    PermissionDeniedError,
)
from app.core.time import ensure_utc, utc_now
from app.models.event import Event
from app.models.party_member import PartyMember
from app.repositories.events import EventRepository
from app.repositories.parties import PartyRepository
from app.repositories.responses import EventResponseRepository
from app.services.dto import EventDetails, EventStats, EventTransition

logger = get_logger(__name__)
WHITESPACE_RE = re.compile(r"\s+")


class EventService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.events = EventRepository(session)
        self.parties = PartyRepository(session)
        self.responses = EventResponseRepository(session)

    @staticmethod
    def normalize_title(title: str) -> str:
        normalized = WHITESPACE_RE.sub(" ", title.strip())
        if not 1 <= len(normalized) <= 100:
            raise InvalidEventTitleError
        return normalized

    async def create_event(
        self,
        party_id: UUID,
        creator_id: UUID,
        event_type: EventType,
        title: str | None = None,
        text: str | None = None,
    ) -> Event:
        event_title = (
            self.normalize_title(title)
            if event_type == EventType.CUSTOM and title is not None
            else event_type.default_title
        )
        if event_type == EventType.CUSTOM and title is None:
            raise InvalidEventTitleError
        now = utc_now()
        try:
            async with self.session.begin():
                await self.events.acquire_creation_lock(party_id, event_type)
                party = await self.parties.get(party_id, for_update=True)
                if party is None:
                    raise PartyNotFoundError
                membership = await self._active_membership(party_id, creator_id)
                if (
                    party.event_creation_policy == EventCreationPolicy.ADMINS_ONLY
                    and membership.role not in {PartyRole.OWNER, PartyRole.ADMIN}
                ):
                    raise PermissionDeniedError
                await self.events.expire_due(now, party_id=party_id, event_type=event_type)
                existing = await self.events.find_active(party_id, event_type, now)
                if existing is not None:
                    raise EventAlreadyExistsError(existing.id)
                await self._check_cooldown(party_id, event_type, now)
                event = self.events.add(
                    party_id=party_id,
                    creator_id=creator_id,
                    event_type=event_type,
                    title=event_title,
                    text=text,
                    expires_at=now + timedelta(minutes=self.settings.event_ttl_minutes(event_type)),
                )
                await self.session.flush()
                await self.responses.upsert(
                    event_id=event.id,
                    user_id=creator_id,
                    response=ResponseType.GOING,
                )
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.events.find_active(party_id, event_type, utc_now())
            if existing is not None:
                raise EventAlreadyExistsError(existing.id) from exc
            raise
        logger.info(
            "event_created",
            event_id=str(event.id),
            party_id=str(party_id),
            creator_id=str(creator_id),
            event_type=event_type.value,
        )
        return event

    async def _check_cooldown(self, party_id: UUID, event_type: EventType, now) -> None:
        cooldown = self.settings.event_cooldown_minutes(event_type)
        if cooldown <= 0:
            return
        latest = await self.events.latest_completed(party_id, event_type)
        if latest is None:
            return
        _, completed_at = latest
        remaining = ensure_utc(completed_at) + timedelta(minutes=cooldown) - now
        if remaining.total_seconds() > 0:
            raise CooldownActiveError(math.ceil(remaining.total_seconds()))

    async def _active_membership(self, party_id: UUID, user_id: UUID) -> PartyMember:
        membership = await self.parties.get_membership(party_id, user_id)
        if membership is None or not membership.is_active:
            raise NotPartyMemberError
        return membership

    async def find_active_event(self, party_id: UUID, event_type: EventType) -> Event | None:
        now = utc_now()
        await self.events.expire_due(now, party_id=party_id, event_type=event_type)
        await self.session.commit()
        return await self.events.find_active(party_id, event_type, now)

    async def respond(self, event_id: UUID, user_id: UUID, response: ResponseType) -> EventDetails:
        now = utc_now()
        expired = False
        response_changed = False
        became_going = False
        async with self.session.begin():
            event = await self.events.get(event_id, for_update=True)
            if event is None:
                raise EventNotFoundError
            await self._active_membership(event.party_id, user_id)
            if event.status == EventStatus.ACTIVE and ensure_utc(event.expires_at) <= now:
                event.status = EventStatus.EXPIRED
                expired = True
            elif event.status != EventStatus.ACTIVE:
                if event.status == EventStatus.EXPIRED:
                    raise EventExpiredError
                raise EventNotActiveError
            else:
                if event.creator_id == user_id and response != ResponseType.GOING:
                    raise PermissionDeniedError
                previous = await self.responses.get_user_response(event_id, user_id)
                previous_response = previous.response if previous is not None else None
                response_changed = previous_response != response
                became_going = response_changed and response == ResponseType.GOING
                if response_changed:
                    await self.responses.upsert(
                        event_id=event_id,
                        user_id=user_id,
                        response=response,
                    )
        if expired:
            raise EventExpiredError
        if response_changed:
            logger.info(
                "event_response_changed",
                event_id=str(event_id),
                user_id=str(user_id),
                response=response.value,
            )
        details = await self.get_event_details(event_id, user_id)
        details.response_changed = response_changed
        details.became_going = became_going
        return details

    async def get_event_details(self, event_id: UUID, requester_id: UUID) -> EventDetails:
        now = utc_now()
        event = await self.events.get(event_id, with_relations=True)
        if event is None:
            raise EventNotFoundError
        membership = await self._active_membership(event.party_id, requester_id)
        if event.status == EventStatus.ACTIVE and ensure_utc(event.expires_at) <= now:
            event.status = EventStatus.EXPIRED
            await self.session.commit()
        counts = await self.responses.counts(event.id, event.party_id)
        users = await self.responses.users_by_response(event.id, event.party_id)
        member_count = await self.parties.count_members(event.party_id)
        response_count = sum(counts.values())
        own_response = await self.responses.get_user_response(event.id, requester_id)
        details = EventDetails(
            event=event,
            requester_membership=membership,
            requester_response=own_response.response if own_response else None,
            stats=EventStats(
                going_count=counts.get(ResponseType.GOING, 0),
                later_count=counts.get(ResponseType.LATER, 0),
                declined_count=counts.get(ResponseType.DECLINED, 0),
                no_response_count=max(0, member_count - response_count),
                going_users=users[ResponseType.GOING],
                later_users=users[ResponseType.LATER],
                declined_users=users[ResponseType.DECLINED],
            ),
        )
        await self.session.commit()
        return details

    async def start_event(self, event_id: UUID, requester_id: UUID) -> EventTransition:
        now = utc_now()
        expired = False
        changed = False
        async with self.session.begin():
            event = await self.events.get(event_id, for_update=True)
            if event is None:
                raise EventNotFoundError
            membership = await self._active_membership(event.party_id, requester_id)
            self._check_manage_permission(event, membership, creator_only=True)
            if event.status != EventStatus.STARTED:
                if event.status == EventStatus.ACTIVE and ensure_utc(event.expires_at) <= now:
                    event.status = EventStatus.EXPIRED
                    expired = True
                elif event.status != EventStatus.ACTIVE:
                    raise EventNotActiveError
                else:
                    event.status = EventStatus.STARTED
                    event.started_at = now
                    changed = True
        if expired:
            raise EventExpiredError
        if changed:
            logger.info("event_started", event_id=str(event_id), requester_id=str(requester_id))
        return EventTransition(event=event, changed=changed)

    async def cancel_event(self, event_id: UUID, requester_id: UUID) -> EventTransition:
        now = utc_now()
        expired = False
        changed = False
        async with self.session.begin():
            event = await self.events.get(event_id, for_update=True)
            if event is None:
                raise EventNotFoundError
            membership = await self._active_membership(event.party_id, requester_id)
            self._check_manage_permission(event, membership, creator_only=False)
            if event.status != EventStatus.CANCELLED:
                if event.status == EventStatus.ACTIVE and ensure_utc(event.expires_at) <= now:
                    event.status = EventStatus.EXPIRED
                    expired = True
                elif event.status != EventStatus.ACTIVE:
                    raise EventNotActiveError
                else:
                    event.status = EventStatus.CANCELLED
                    event.cancelled_at = now
                    changed = True
        if expired:
            raise EventExpiredError
        if changed:
            logger.info(
                "event_cancelled",
                event_id=str(event_id),
                requester_id=str(requester_id),
            )
        return EventTransition(event=event, changed=changed)

    @staticmethod
    def _check_manage_permission(
        event: Event, membership: PartyMember, *, creator_only: bool
    ) -> None:
        if membership.user_id == event.creator_id:
            return
        if not creator_only and membership.role in {PartyRole.OWNER, PartyRole.ADMIN}:
            return
        raise PermissionDeniedError

    async def expire_due_events(self) -> int:
        async with self.session.begin():
            count = await self.events.expire_due(utc_now())
        if count:
            logger.info("events_expired", count=count)
        return count
