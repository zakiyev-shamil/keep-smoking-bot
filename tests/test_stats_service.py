from app.core.enums import EventType, ResponseType
from app.services.event_service import EventService
from app.services.stats_service import StatsService
from tests.helpers import make_settings, party_with_members


async def test_stats_count_only_started_participation(session):
    party, users = await party_with_members(session)
    events = EventService(session, make_settings(smoke_cooldown_minutes=0))

    started = await events.create_event(party.id, users[0].id, EventType.SMOKE)
    await events.respond(started.id, users[1].id, ResponseType.LATER)
    await events.start_event(started.id, users[0].id)
    await events.create_event(party.id, users[0].id, EventType.LUNCH)

    member_stats = await StatsService(session).get_user_party_stats(
        party.id,
        users[1].id,
    )
    creator_stats = await StatsService(session).get_user_party_stats(
        party.id,
        users[0].id,
    )

    assert member_stats.participation_by_type[EventType.SMOKE] == 1
    assert member_stats.participation_by_type.get(EventType.LUNCH, 0) == 0
    assert member_stats.created_count == 0
    assert creator_stats.participation_by_type[EventType.SMOKE] == 1
    assert creator_stats.created_count == 1
