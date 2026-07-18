from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventStatus, EventType, ResponseType
from app.models.event import Event
from app.models.event_response import EventResponse


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def participation_by_type(
        self,
        *,
        party_id: UUID,
        user_id: UUID,
    ) -> dict[EventType, int]:
        rows = (
            await self.session.execute(
                select(Event.type, func.count(Event.id))
                .join(EventResponse, EventResponse.event_id == Event.id)
                .where(
                    Event.party_id == party_id,
                    Event.status == EventStatus.STARTED,
                    EventResponse.user_id == user_id,
                    EventResponse.response.in_([ResponseType.GOING, ResponseType.LATER]),
                )
                .group_by(Event.type)
            )
        ).all()
        return {event_type: int(count) for event_type, count in rows}

    async def started_events_created(
        self,
        *,
        party_id: UUID,
        creator_id: UUID,
    ) -> int:
        return int(
            await self.session.scalar(
                select(func.count(Event.id)).where(
                    Event.party_id == party_id,
                    Event.creator_id == creator_id,
                    Event.status == EventStatus.STARTED,
                )
            )
            or 0
        )
