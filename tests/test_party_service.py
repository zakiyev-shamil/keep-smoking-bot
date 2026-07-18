from app.core.enums import PartyRole
from app.services.invitation_service import InvitationService
from app.services.party_service import PartyService
from tests.helpers import add_user


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
