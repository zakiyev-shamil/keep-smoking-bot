from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.enums import EventStatus, EventType, PartyRole, ResponseType
from app.core.exceptions import (
    CooldownActiveError,
    EventAlreadyExistsError,
    EventExpiredError,
    PermissionDeniedError,
)
from app.core.time import utc_now
from app.models.event_response import EventResponse
from app.services.event_service import EventService
from tests.helpers import make_settings, party_with_members


async def test_create_event_adds_creator_as_going(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())

    event = await service.create_event(party.id, users[0].id, EventType.SMOKE)
    response = await session.scalar(
        select(EventResponse).where(
            EventResponse.event_id == event.id,
            EventResponse.user_id == users[0].id,
        )
    )

    assert event.status == EventStatus.ACTIVE
    assert response is not None
    assert response.response == ResponseType.GOING


async def test_duplicate_active_event_is_rejected(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    existing = await service.create_event(party.id, users[0].id, EventType.SMOKE)
    existing_id = existing.id

    with pytest.raises(EventAlreadyExistsError) as error:
        await service.create_event(party.id, users[1].id, EventType.SMOKE)

    assert error.value.event_id == existing_id


async def test_cooldown_after_started_event(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.SMOKE)
    transition = await service.start_event(event.id, users[0].id)

    assert transition.changed is True
    with pytest.raises(CooldownActiveError):
        await service.create_event(party.id, users[0].id, EventType.SMOKE)


async def test_response_is_updated_not_duplicated(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.COFFEE)

    await service.respond(event.id, users[1].id, ResponseType.LATER)
    details = await service.respond(event.id, users[1].id, ResponseType.GOING)
    responses = (
        await session.scalars(
            select(EventResponse).where(
                EventResponse.event_id == event.id,
                EventResponse.user_id == users[1].id,
            )
        )
    ).all()

    assert len(responses) == 1
    assert responses[0].response == ResponseType.GOING
    assert details.stats.going_count == 2


async def test_response_reports_only_real_transition_to_going(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.SMOKE)

    later = await service.respond(event.id, users[1].id, ResponseType.LATER)
    going = await service.respond(event.id, users[1].id, ResponseType.GOING)
    repeated = await service.respond(event.id, users[1].id, ResponseType.GOING)

    assert later.response_changed is True
    assert later.became_going is False
    assert going.response_changed is True
    assert going.became_going is True
    assert repeated.response_changed is False
    assert repeated.became_going is False


async def test_creator_cannot_decline_own_event(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.SMOKE)
    event_id = event.id
    creator_id = users[0].id

    with pytest.raises(PermissionDeniedError):
        await service.respond(event_id, creator_id, ResponseType.DECLINED)

    response = await session.scalar(
        select(EventResponse).where(
            EventResponse.event_id == event_id,
            EventResponse.user_id == creator_id,
        )
    )
    assert response is not None
    assert response.response == ResponseType.GOING


async def test_expired_event_is_persisted_and_cannot_be_answered(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.LUNCH)
    event.expires_at = utc_now() - timedelta(seconds=1)
    await session.commit()

    with pytest.raises(EventExpiredError):
        await service.respond(event.id, users[1].id, ResponseType.GOING)

    await session.refresh(event)
    assert event.status == EventStatus.EXPIRED


async def test_cancel_permissions_and_admin_cancel(session):
    party, users = await party_with_members(session, members=3)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.LUNCH)
    event_id = event.id
    party_id = party.id
    member_id = users[1].id
    admin_id = users[2].id

    with pytest.raises(PermissionDeniedError):
        await service.cancel_event(event_id, member_id)

    membership = await service.parties.get_membership(party_id, admin_id)
    membership.role = PartyRole.ADMIN
    await session.commit()
    transition = await service.cancel_event(event_id, admin_id)
    assert transition.event.status == EventStatus.CANCELLED
    assert transition.changed is True


async def test_only_creator_can_start(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.CUSTOM, title="CS")
    event_id = event.id
    creator_id = users[0].id
    member_id = users[1].id

    with pytest.raises(PermissionDeniedError):
        await service.start_event(event_id, member_id)

    transition = await service.start_event(event_id, creator_id)
    assert transition.event.status == EventStatus.STARTED


async def test_start_and_cancel_are_idempotent(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(party.id, users[0].id, EventType.COFFEE)

    first = await service.start_event(event.id, users[0].id)
    second = await service.start_event(event.id, users[0].id)

    assert first.changed is True
    assert second.changed is False
