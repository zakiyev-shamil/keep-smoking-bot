from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotPartyMemberError, PartyNotFoundError
from app.repositories.parties import PartyRepository
from app.repositories.stats import StatsRepository
from app.services.dto import UserPartyStats


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.parties = PartyRepository(session)
        self.stats = StatsRepository(session)

    async def get_user_party_stats(
        self,
        party_id: UUID,
        user_id: UUID,
    ) -> UserPartyStats:
        party = await self.parties.get(party_id)
        if party is None:
            raise PartyNotFoundError
        membership = await self.parties.get_membership(party_id, user_id)
        if membership is None or not membership.is_active:
            raise NotPartyMemberError
        participation = await self.stats.participation_by_type(
            party_id=party_id,
            user_id=user_id,
        )
        created_count = await self.stats.started_events_created(
            party_id=party_id,
            creator_id=user_id,
        )
        return UserPartyStats(
            party=party,
            participation_by_type=participation,
            created_count=created_count,
        )
