from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.enums import EventCreationPolicy, PartyRole
from app.models.party import Party
from app.models.party_member import PartyMember
from app.models.user import User


class PartyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, party_id: UUID, *, for_update: bool = False) -> Party | None:
        statement = select(Party).where(Party.id == party_id, Party.is_active.is_(True))
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_by_invite(self, token: str) -> Party | None:
        return await self.session.scalar(
            select(Party).where(Party.invite_code == token, Party.is_active.is_(True))
        )

    def add(
        self,
        *,
        owner_id: UUID,
        name: str,
        invite_code: str,
        event_creation_policy: EventCreationPolicy = EventCreationPolicy.EVERYONE,
    ) -> Party:
        party = Party(
            owner_id=owner_id,
            name=name,
            invite_code=invite_code,
            event_creation_policy=event_creation_policy,
        )
        self.session.add(party)
        return party

    def add_member(self, *, party_id: UUID, user_id: UUID, role: PartyRole) -> PartyMember:
        member = PartyMember(party_id=party_id, user_id=user_id, role=role, is_active=True)
        self.session.add(member)
        return member

    async def get_membership(
        self, party_id: UUID, user_id: UUID, *, for_update: bool = False
    ) -> PartyMember | None:
        statement = select(PartyMember).where(
            PartyMember.party_id == party_id,
            PartyMember.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def get_membership_by_id(
        self, membership_id: UUID, *, for_update: bool = False
    ) -> PartyMember | None:
        statement = select(PartyMember).where(PartyMember.id == membership_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def list_for_user(self, user_id: UUID) -> list[Party]:
        result = await self.session.scalars(
            select(Party)
            .join(PartyMember, PartyMember.party_id == Party.id)
            .where(
                PartyMember.user_id == user_id,
                PartyMember.is_active.is_(True),
                Party.is_active.is_(True),
            )
            .order_by(Party.name, Party.id)
        )
        return list(result)

    async def count_members(self, party_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count(PartyMember.id)).where(
                    PartyMember.party_id == party_id,
                    PartyMember.is_active.is_(True),
                )
            )
            or 0
        )

    async def list_members(self, party_id: UUID, *, offset: int, limit: int) -> list[PartyMember]:
        result = await self.session.scalars(
            select(PartyMember)
            .join(User, User.id == PartyMember.user_id)
            .options(joinedload(PartyMember.user))
            .where(PartyMember.party_id == party_id, PartyMember.is_active.is_(True))
            .order_by(
                PartyMember.joined_at,
                User.first_name,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.unique())
