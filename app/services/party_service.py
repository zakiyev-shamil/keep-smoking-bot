from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import get_logger

from app.core.enums import PartyRole
from app.core.exceptions import (
    InvalidInvitationError,
    NotPartyMemberError,
    PartyNameInvalidError,
    PartyNotFoundError,
    PermissionDeniedError,
)
from app.core.security import mask_token
from app.models.party import Party
from app.models.party_member import PartyMember
from app.repositories.parties import PartyRepository
from app.repositories.users import UserRepository
from app.services.invitation_service import InvitationService

logger = get_logger(__name__)
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class JoinPartyResult:
    party: Party
    joined: bool


class PartyService:
    def __init__(
        self,
        session: AsyncSession,
        invitation_service: InvitationService,
    ) -> None:
        self.session = session
        self.repository = PartyRepository(session)
        self.users = UserRepository(session)
        self.invitations = invitation_service

    @staticmethod
    def normalize_name(name: str) -> str:
        normalized = WHITESPACE_RE.sub(" ", name.strip())
        if not 1 <= len(normalized) <= 100:
            raise PartyNameInvalidError
        return normalized

    async def create_party(self, creator_user_id: UUID, name: str) -> Party:
        normalized_name = self.normalize_name(name)
        token = self.invitations.new_token()
        try:
            async with self.session.begin():
                party = self.repository.add(
                    owner_id=creator_user_id,
                    name=normalized_name,
                    invite_code=token,
                )
                await self.session.flush()
                self.repository.add_member(
                    party_id=party.id,
                    user_id=creator_user_id,
                    role=PartyRole.OWNER,
                )
        except IntegrityError:
            await self.session.rollback()
            token = self.invitations.new_token()
            async with self.session.begin():
                party = self.repository.add(
                    owner_id=creator_user_id,
                    name=normalized_name,
                    invite_code=token,
                )
                await self.session.flush()
                self.repository.add_member(
                    party_id=party.id,
                    user_id=creator_user_id,
                    role=PartyRole.OWNER,
                )
        await self.set_active_party(creator_user_id, party.id)
        logger.info(
            "party_created",
            party_id=str(party.id),
            owner_id=str(creator_user_id),
            invite_token=mask_token(token),
        )
        return party

    async def join_party(self, user_id: UUID, invite_token: str) -> JoinPartyResult:
        if not invite_token or len(invite_token) > 64:
            raise InvalidInvitationError
        try:
            async with self.session.begin():
                party = await self.repository.get_by_invite(invite_token)
                if party is None:
                    raise InvalidInvitationError
                membership = await self.repository.get_membership(
                    party.id, user_id, for_update=True
                )
                if membership is not None:
                    joined = not membership.is_active
                    membership.is_active = True
                else:
                    self.repository.add_member(
                        party_id=party.id,
                        user_id=user_id,
                        role=PartyRole.MEMBER,
                    )
                    joined = True
        except IntegrityError:
            await self.session.rollback()
            party = await self.repository.get_by_invite(invite_token)
            if party is None:
                raise InvalidInvitationError from None
            membership = await self.repository.get_membership(party.id, user_id)
            if membership is None:
                raise
            joined = False
            await self.session.commit()
        await self.set_active_party(user_id, party.id)
        if joined:
            logger.info(
                "party_joined",
                party_id=str(party.id),
                user_id=str(user_id),
                invite_token=mask_token(invite_token),
            )
        return JoinPartyResult(party=party, joined=joined)

    async def get_user_parties(self, user_id: UUID) -> list[Party]:
        return await self.repository.list_for_user(user_id)

    async def get_party_for_member(
        self, party_id: UUID, user_id: UUID
    ) -> tuple[Party, PartyMember]:
        party = await self.repository.get(party_id)
        if party is None:
            raise PartyNotFoundError
        membership = await self.repository.get_membership(party_id, user_id)
        if membership is None or not membership.is_active:
            raise NotPartyMemberError
        return party, membership

    async def get_party_members(
        self, party_id: UUID, requester_id: UUID, page: int, page_size: int = 10
    ) -> tuple[Party, PartyMember, list[PartyMember], int]:
        party, requester = await self.get_party_for_member(party_id, requester_id)
        total = await self.repository.count_members(party_id)
        safe_page = max(0, page)
        members = await self.repository.list_members(
            party_id, offset=safe_page * page_size, limit=page_size
        )
        return party, requester, members, total

    async def count_members(self, party_id: UUID) -> int:
        return await self.repository.count_members(party_id)

    async def set_member_role(
        self,
        party_id: UUID,
        requester_id: UUID,
        member_user_id: UUID,
        role: PartyRole,
    ) -> PartyMember:
        if role == PartyRole.OWNER:
            raise PermissionDeniedError
        async with self.session.begin():
            party = await self.repository.get(party_id, for_update=True)
            if party is None:
                raise PartyNotFoundError
            requester = await self.repository.get_membership(party_id, requester_id)
            if requester is None or not requester.is_active:
                raise NotPartyMemberError
            if requester.role != PartyRole.OWNER:
                raise PermissionDeniedError
            target = await self.repository.get_membership(party_id, member_user_id, for_update=True)
            if target is None or not target.is_active or target.role == PartyRole.OWNER:
                raise PermissionDeniedError
            target.role = role
        return target

    async def set_membership_role(
        self,
        membership_id: UUID,
        requester_id: UUID,
        role: PartyRole,
    ) -> PartyMember:
        if role == PartyRole.OWNER:
            raise PermissionDeniedError
        async with self.session.begin():
            target = await self.repository.get_membership_by_id(membership_id, for_update=True)
            if target is None or not target.is_active or target.role == PartyRole.OWNER:
                raise NotPartyMemberError
            requester = await self.repository.get_membership(target.party_id, requester_id)
            if requester is None or not requester.is_active or requester.role != PartyRole.OWNER:
                raise PermissionDeniedError
            target.role = role
        return target

    async def set_active_party(self, user_id: UUID, party_id: UUID) -> None:
        await self.users.set_active_party_id(user_id, party_id)
        await self.session.commit()

    async def get_active_party(self, user_id: UUID) -> Party | None:
        active_party_id = await self.users.get_active_party_id(user_id)
        if active_party_id is not None:
            try:
                party, _ = await self.get_party_for_member(active_party_id, user_id)
                return party
            except (PartyNotFoundError, NotPartyMemberError):
                pass
        parties = await self.get_user_parties(user_id)
        if not parties:
            return None
        await self.set_active_party(user_id, parties[0].id)
        return parties[0]
