from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.enums import EventStatus, EventType, PartyRole, ResponseType
from app.core.exceptions import DomainError
from app.core.time import utc_now
from app.database.base import Base
from app.models.event import Event
from app.models.event_response import EventResponse
from app.models.party_member import PartyMember
from app.services.event_service import EventService
from app.services.stats_service import StatsService
from tests.helpers import add_user, make_settings, party_with_members

ACTION_NAMES = ("create", "respond", "start", "cancel", "expire", "stats")
EVENT_TYPES = (EventType.SMOKE, EventType.LUNCH, EventType.CUSTOM)
RESPONSES = (ResponseType.GOING, ResponseType.LATER, ResponseType.DECLINED)
TITLES = ("Настолки", "  Пинг-понг  ", "", "x" * 101, "<b>CS</b>")

action_strategy = st.tuples(
    st.sampled_from(ACTION_NAMES),
    st.integers(min_value=0, max_value=3),
    st.sampled_from(EVENT_TYPES),
    st.sampled_from(RESPONSES),
    st.integers(min_value=0, max_value=20),
    st.sampled_from(TITLES),
)


async def _events(session: AsyncSession, party_id: UUID) -> list[Event]:
    result = await session.scalars(
        select(Event).where(Event.party_id == party_id).order_by(Event.created_at, Event.id)
    )
    return list(result)


async def _assert_invariants(session: AsyncSession, party_id: UUID) -> None:
    active_duplicates = (
        await session.execute(
            select(Event.type, func.count(Event.id))
            .where(
                Event.party_id == party_id,
                Event.status == EventStatus.ACTIVE,
            )
            .group_by(Event.type)
            .having(func.count(Event.id) > 1)
        )
    ).all()
    assert active_duplicates == []

    duplicate_responses = (
        await session.execute(
            select(
                EventResponse.event_id,
                EventResponse.user_id,
                func.count(EventResponse.id),
            )
            .group_by(EventResponse.event_id, EventResponse.user_id)
            .having(func.count(EventResponse.id) > 1)
        )
    ).all()
    assert duplicate_responses == []

    outsider_responses = list(
        await session.scalars(
            select(EventResponse.id)
            .join(Event, Event.id == EventResponse.event_id)
            .outerjoin(
                PartyMember,
                and_(
                    PartyMember.party_id == Event.party_id,
                    PartyMember.user_id == EventResponse.user_id,
                    PartyMember.is_active.is_(True),
                ),
            )
            .where(
                Event.party_id == party_id,
                PartyMember.id.is_(None),
            )
        )
    )
    assert outsider_responses == []

    for event in await _events(session, party_id):
        creator_response = await session.scalar(
            select(EventResponse).where(
                EventResponse.event_id == event.id,
                EventResponse.user_id == event.creator_id,
            )
        )
        assert creator_response is not None
        assert creator_response.response == ResponseType.GOING
        if event.status == EventStatus.STARTED:
            assert event.started_at is not None
        if event.status == EventStatus.CANCELLED:
            assert event.cancelled_at is not None


async def _exercise(
    actions: list[tuple[str, int, EventType, ResponseType, int, str]],
) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app_settings = make_settings(
        smoke_cooldown_minutes=0,
        lunch_cooldown_minutes=0,
        custom_cooldown_minutes=0,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            party, members = await party_with_members(session, members=3)
            outsider = await add_user(session, 9999, "Outsider")
            admin_membership = await session.scalar(
                select(PartyMember).where(
                    PartyMember.party_id == party.id,
                    PartyMember.user_id == members[2].id,
                )
            )
            assert admin_membership is not None
            admin_membership.role = PartyRole.ADMIN
            await session.commit()
            party_id = party.id
            user_ids = [member.id for member in members] + [outsider.id]
            await EventService(session, app_settings).create_event(
                party_id,
                user_ids[0],
                EventType.SMOKE,
            )

        for action, actor_index, event_type, response, slot, title in actions:
            async with factory() as session:
                service = EventService(session, app_settings)
                actor_id = user_ids[actor_index]
                existing_ids = list(
                    await session.scalars(
                        select(Event.id)
                        .where(Event.party_id == party_id)
                        .order_by(Event.created_at, Event.id)
                    )
                )
                target_id = existing_ids[slot % len(existing_ids)] if existing_ids else None
                await session.rollback()
                try:
                    if action == "create":
                        await service.create_event(
                            party_id,
                            actor_id,
                            event_type,
                            title=title if event_type == EventType.CUSTOM else None,
                        )
                    elif action == "respond" and target_id is not None:
                        await service.respond(target_id, actor_id, response)
                    elif action == "start" and target_id is not None:
                        await service.start_event(target_id, actor_id)
                    elif action == "cancel" and target_id is not None:
                        await service.cancel_event(target_id, actor_id)
                    elif action == "expire" and target_id is not None:
                        target = await session.get(Event, target_id)
                        assert target is not None
                        if target.status == EventStatus.ACTIVE:
                            target.expires_at = utc_now() - timedelta(seconds=1)
                            await session.commit()
                            await service.get_event_details(target_id, members[0].id)
                    elif action == "stats":
                        await StatsService(session).get_user_party_stats(
                            party_id,
                            actor_id,
                        )
                except DomainError:
                    # Invalid random transitions are expected; invariants must still hold.
                    pass

            async with factory() as invariant_session:
                await _assert_invariants(invariant_session, party_id)
    finally:
        await engine.dispose()


@settings(
    max_examples=25,
    deadline=None,
    derandomize=True,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
@example(
    actions=[
        (
            "respond",
            0,
            EventType.SMOKE,
            ResponseType.DECLINED,
            0,
            "Настолки",
        )
    ]
)
@given(actions=st.lists(action_strategy, min_size=5, max_size=30))
def test_randomized_event_state_machine(
    fuzz_runner: asyncio.Runner,
    actions: list[tuple[str, int, EventType, ResponseType, int, str]],
) -> None:
    fuzz_runner.run(_exercise(actions))


@pytest.fixture(scope="module")
def fuzz_runner() -> asyncio.Runner:
    with asyncio.Runner() as runner:
        yield runner
