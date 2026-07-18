from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.enums import EventStatus, EventType, ResponseType
from app.core.exceptions import (
    EventExpiredError,
    EventNotActiveError,
    InvalidPollOptionError,
    InvalidPollOptionsError,
)
from app.core.time import utc_now
from app.models.event_poll_vote import EventPollVote
from app.services.event_service import EventService
from tests.helpers import make_settings, party_with_members


async def test_create_poll_and_upsert_vote_switches_option(session):
    party, users = await party_with_members(session, members=3)
    service = EventService(session, make_settings())
    event = await service.create_event(
        party.id,
        users[0].id,
        EventType.LUNCH,
        poll_options=["Плов", "Пицца", "Бургеры"],
    )
    initial = await service.get_event_details(event.id, users[1].id)

    assert initial.poll is not None
    assert [option.text for option in initial.poll.options] == ["Плов", "Пицца", "Бургеры"]
    assert [option.vote_count for option in initial.poll.options] == [0, 0, 0]

    first = await service.vote_poll(event.id, users[1].id, initial.poll.options[0].id)
    switched = await service.vote_poll(event.id, users[1].id, initial.poll.options[1].id)
    vote_count = await session.scalar(
        select(func.count(EventPollVote.id)).where(
            EventPollVote.event_id == event.id,
            EventPollVote.user_id == users[1].id,
        )
    )

    assert first.requester_response == ResponseType.GOING
    assert first.response_changed is True
    assert first.poll_changed is True
    assert switched.response_changed is False
    assert switched.poll_changed is True
    assert switched.poll is not None
    assert [option.vote_count for option in switched.poll.options] == [0, 1, 0]
    assert switched.poll.selected_option_id == initial.poll.options[1].id
    assert vote_count == 1


async def test_indifferent_clears_vote_and_sets_going(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(
        party.id,
        users[0].id,
        EventType.LUNCH,
        poll_options=["Плов", "Пицца"],
    )
    details = await service.get_event_details(event.id, users[1].id)
    assert details.poll is not None
    await service.vote_poll(event.id, users[1].id, details.poll.options[0].id)
    indifferent = await service.vote_poll(event.id, users[1].id, None)

    assert indifferent.requester_response == ResponseType.GOING
    assert indifferent.poll is not None
    assert indifferent.poll.selected_option_id is None
    assert [option.vote_count for option in indifferent.poll.options] == [0, 0]


async def test_later_preserves_vote_and_declined_removes_it(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(
        party.id,
        users[0].id,
        EventType.LUNCH,
        poll_options=["Плов", "Пицца"],
    )
    details = await service.get_event_details(event.id, users[1].id)
    assert details.poll is not None
    selected_id = details.poll.options[0].id
    await service.vote_poll(event.id, users[1].id, selected_id)

    later = await service.respond(event.id, users[1].id, ResponseType.LATER)
    declined = await service.respond(event.id, users[1].id, ResponseType.DECLINED)

    assert later.poll is not None
    assert later.poll.selected_option_id == selected_id
    assert declined.poll is not None
    assert declined.poll.selected_option_id is None
    assert declined.poll.options[0].vote_count == 0


async def test_vote_rejects_expired_started_and_forged_options(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())
    event = await service.create_event(
        party.id,
        users[0].id,
        EventType.LUNCH,
        poll_options=["Плов", "Пицца"],
    )
    event_id = event.id
    creator_id = users[0].id
    member_id = users[1].id

    with pytest.raises(InvalidPollOptionError):
        await service.vote_poll(event_id, member_id, uuid4())

    details = await service.get_event_details(event_id, member_id)
    assert details.poll is not None
    await service.start_event(event_id, creator_id)
    with pytest.raises(EventNotActiveError):
        await service.vote_poll(event_id, member_id, details.poll.options[0].id)

    other_party, other_users = await party_with_members(session, telegram_start=2000)
    expired = await service.create_event(
        other_party.id,
        other_users[0].id,
        EventType.LUNCH,
        poll_options=["Лагман", "Манты"],
    )
    expired.expires_at = utc_now() - timedelta(seconds=1)
    await session.commit()
    expired_details = await service.get_event_details(expired.id, other_users[1].id)
    assert expired_details.poll is not None
    assert expired_details.event.status == EventStatus.EXPIRED
    with pytest.raises(EventExpiredError):
        await service.vote_poll(
            expired.id,
            other_users[1].id,
            expired_details.poll.options[0].id,
        )


async def test_poll_option_must_belong_to_same_event(session):
    first_party, first_users = await party_with_members(session)
    second_party, second_users = await party_with_members(session, telegram_start=2000)
    service = EventService(session, make_settings())
    first = await service.create_event(
        first_party.id,
        first_users[0].id,
        EventType.LUNCH,
        poll_options=["A", "B"],
    )
    second = await service.create_event(
        second_party.id,
        second_users[0].id,
        EventType.LUNCH,
        poll_options=["C", "D"],
    )
    second_details = await service.get_event_details(second.id, second_users[1].id)
    assert second_details.poll is not None

    with pytest.raises(InvalidPollOptionError):
        await service.vote_poll(
            first.id,
            first_users[1].id,
            second_details.poll.options[0].id,
        )


async def test_create_poll_rejects_non_lunch_and_invalid_options(session):
    party, users = await party_with_members(session)
    service = EventService(session, make_settings())

    with pytest.raises(InvalidPollOptionsError):
        await service.create_event(
            party.id,
            users[0].id,
            EventType.SMOKE,
            poll_options=["A", "B"],
        )
    with pytest.raises(InvalidPollOptionsError):
        await service.create_event(
            party.id,
            users[0].id,
            EventType.LUNCH,
            poll_options=["A"],
        )
