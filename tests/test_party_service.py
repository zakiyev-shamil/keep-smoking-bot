import pytest
from sqlalchemy import func, select

from app.core.enums import EventType, NotificationStatus, PartyRole
from app.core.exceptions import InvalidInvitationError, PermissionDeniedError
from app.models.event import Event
from app.models.event_poll_option import EventPollOption
from app.models.event_poll_vote import EventPollVote
from app.models.event_response import EventResponse
from app.models.notification import Notification
from app.models.party import Party
from app.models.party_member import PartyMember
from app.models.user_runtime_state import UserRuntimeState
from app.services.event_service import EventService
from app.services.invitation_service import InvitationService
from app.services.party_service import PartyService
from tests.helpers import add_user, make_settings


async def test_create_party_creates_owner_membership(session):
    owner = await add_user(session, 1, "Artem")
    service = PartyService(session, InvitationService())

    party = await service.create_party(owner.id, "  Backend  ")
    membership = await service.repository.get_membership(party.id, owner.id)

    assert party.name == "Backend"
    assert len(party.invite_code) >= 32
    assert membership is not None
    assert membership.role == PartyRole.OWNER


async def test_join_and_duplicate_join_are_idempotent(session):
    owner = await add_user(session, 1, "Artem")
    colleague = await add_user(session, 2, "Max")
    service = PartyService(session, InvitationService())
    party = await service.create_party(owner.id, "Backend")

    first = await service.join_party(colleague.id, party.invite_code)
    second = await service.join_party(colleague.id, party.invite_code)

    assert first.joined is True
    assert second.joined is False
    assert await service.count_members(party.id) == 2


async def test_only_owner_can_delete_party(session):
    owner = await add_user(session, 1, "Artem")
    colleague = await add_user(session, 2, "Max")
    service = PartyService(session, InvitationService())
    party = await service.create_party(owner.id, "Backend")
    await service.join_party(colleague.id, party.invite_code)
    party_id = party.id
    colleague_id = colleague.id

    with pytest.raises(PermissionDeniedError):
        await service.delete_party(party_id, colleague_id)

    assert await service.repository.get(party_id) is not None


async def test_delete_party_removes_complete_tree_and_runtime_selection(session):
    owner = await add_user(session, 1, "Artem")
    colleague = await add_user(session, 2, "Max")
    service = PartyService(session, InvitationService())
    party = await service.create_party(owner.id, "Backend")
    await service.join_party(colleague.id, party.invite_code)
    event_service = EventService(session, make_settings())
    event = await event_service.create_event(
        party.id,
        owner.id,
        EventType.LUNCH,
        poll_options=["Плов", "Пицца"],
    )
    details = await event_service.get_event_details(event.id, colleague.id)
    assert details.poll is not None
    await event_service.vote_poll(
        event.id,
        colleague.id,
        details.poll.options[0].id,
    )
    session.add(
        Notification(
            event_id=event.id,
            recipient_id=colleague.id,
            status=NotificationStatus.SENT,
            telegram_message_id=100,
        )
    )
    await session.commit()
    invite_code = party.invite_code
    party_id = party.id
    colleague_id = colleague.id

    deleted_name = await service.delete_party(party_id, owner.id)

    assert deleted_name == "Backend"
    for model in (
        Party,
        PartyMember,
        Event,
        EventResponse,
        EventPollOption,
        EventPollVote,
        Notification,
    ):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
    active_party_ids = list(await session.scalars(select(UserRuntimeState.active_party_id)))
    assert active_party_ids == [None, None]
    await session.rollback()
    with pytest.raises(InvalidInvitationError):
        await service.join_party(colleague_id, invite_code)
