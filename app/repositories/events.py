from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.enums import EventStatus, EventType
from app.models.event import Event


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def acquire_creation_lock(self, party_id: UUID, event_type: EventType) -> None:
        bind = self.session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        digest = hashlib.blake2b(f"{party_id}:{event_type.value}".encode(), digest_size=8).digest()
        lock_key = int.from_bytes(digest, byteorder="big", signed=True)
        await self.session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def expire_due(
        self,
        now: datetime,
        *,
        party_id: UUID | None = None,
        event_type: EventType | None = None,
    ) -> int:
        conditions = [
            Event.status == EventStatus.ACTIVE,
            Event.expires_at <= now,
        ]
        if party_id is not None:
            conditions.append(Event.party_id == party_id)
        if event_type is not None:
            conditions.append(Event.type == event_type)
        result = await self.session.execute(
            update(Event).where(*conditions).values(status=EventStatus.EXPIRED, updated_at=now)
        )
        return int(result.rowcount or 0)

    async def find_active(
        self, party_id: UUID, event_type: EventType, now: datetime
    ) -> Event | None:
        return await self.session.scalar(
            select(Event)
            .options(joinedload(Event.creator), joinedload(Event.party))
            .where(
                Event.party_id == party_id,
                Event.type == event_type,
                Event.status == EventStatus.ACTIVE,
                Event.expires_at > now,
            )
            .order_by(Event.created_at.desc())
        )

    async def latest_completed(
        self, party_id: UUID, event_type: EventType
    ) -> tuple[Event, datetime] | None:
        completed_at = case(
            (Event.status == EventStatus.STARTED, Event.started_at),
            (Event.status == EventStatus.CANCELLED, Event.cancelled_at),
            (Event.status == EventStatus.EXPIRED, Event.expires_at),
            else_=Event.updated_at,
        )
        row = (
            await self.session.execute(
                select(Event, completed_at.label("completed_at"))
                .where(
                    Event.party_id == party_id,
                    Event.type == event_type,
                    Event.status != EventStatus.ACTIVE,
                )
                .order_by(completed_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        return row[0], row.completed_at

    def add(
        self,
        *,
        party_id: UUID,
        creator_id: UUID,
        event_type: EventType,
        title: str,
        text: str | None,
        expires_at: datetime,
    ) -> Event:
        event = Event(
            party_id=party_id,
            creator_id=creator_id,
            type=event_type,
            title=title,
            text=text,
            status=EventStatus.ACTIVE,
            expires_at=expires_at,
        )
        self.session.add(event)
        return event

    async def get(
        self,
        event_id: UUID,
        *,
        for_update: bool = False,
        with_relations: bool = False,
    ) -> Event | None:
        statement = select(Event).where(Event.id == event_id)
        if with_relations:
            statement = statement.options(joinedload(Event.creator), joinedload(Event.party))
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def set_creator_view(
        self,
        *,
        event_id: UUID,
        creator_id: UUID,
        chat_id: int,
        message_id: int,
    ) -> bool:
        result = await self.session.execute(
            update(Event)
            .where(Event.id == event_id, Event.creator_id == creator_id)
            .values(
                creator_chat_id=chat_id,
                creator_message_id=message_id,
            )
        )
        return bool(result.rowcount)

    async def list_recent_active(
        self, party_id: UUID, now: datetime, limit: int = 10
    ) -> list[Event]:
        result = await self.session.scalars(
            select(Event)
            .options(joinedload(Event.creator))
            .where(
                Event.party_id == party_id,
                Event.status == EventStatus.ACTIVE,
                Event.expires_at > now,
            )
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
        return list(result.unique())
