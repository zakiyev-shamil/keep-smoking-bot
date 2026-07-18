from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ResponseType
from app.models.event_response import EventResponse
from app.models.party_member import PartyMember
from app.models.user import User


class EventResponseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self, *, event_id: UUID, user_id: UUID, response: ResponseType
    ) -> EventResponse:
        bind = self.session.get_bind()
        values = {"event_id": event_id, "user_id": user_id, "response": response}
        if bind.dialect.name == "postgresql":
            statement = postgresql_insert(EventResponse).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[EventResponse.event_id, EventResponse.user_id],
                set_={"response": response, "updated_at": func.now()},
            )
            await self.session.execute(statement)
        elif bind.dialect.name == "sqlite":
            statement = sqlite_insert(EventResponse).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[EventResponse.event_id, EventResponse.user_id],
                set_={"response": response, "updated_at": func.now()},
            )
            await self.session.execute(statement)
        else:
            existing = await self.session.scalar(
                select(EventResponse).where(
                    EventResponse.event_id == event_id,
                    EventResponse.user_id == user_id,
                )
            )
            if existing is None:
                self.session.add(EventResponse(**values))
            else:
                existing.response = response
        await self.session.flush()
        return await self.session.scalar(
            select(EventResponse).where(
                EventResponse.event_id == event_id,
                EventResponse.user_id == user_id,
            )
        )

    async def counts(self, event_id: UUID, party_id: UUID) -> dict[ResponseType, int]:
        rows = (
            await self.session.execute(
                select(EventResponse.response, func.count(EventResponse.id))
                .join(
                    PartyMember,
                    (PartyMember.user_id == EventResponse.user_id)
                    & (PartyMember.party_id == party_id)
                    & PartyMember.is_active.is_(True),
                )
                .where(EventResponse.event_id == event_id)
                .group_by(EventResponse.response)
            )
        ).all()
        return {response: int(count) for response, count in rows}

    async def users_by_response(
        self, event_id: UUID, party_id: UUID
    ) -> dict[ResponseType, list[User]]:
        rows = (
            await self.session.execute(
                select(EventResponse.response, User)
                .join(User, User.id == EventResponse.user_id)
                .join(
                    PartyMember,
                    (PartyMember.user_id == EventResponse.user_id)
                    & (PartyMember.party_id == party_id)
                    & PartyMember.is_active.is_(True),
                )
                .where(EventResponse.event_id == event_id)
                .order_by(User.first_name, User.id)
            )
        ).all()
        result: dict[ResponseType, list[User]] = {
            ResponseType.GOING: [],
            ResponseType.LATER: [],
            ResponseType.DECLINED: [],
        }
        for response, user in rows:
            result[response].append(user)
        return result

    async def get_user_response(self, event_id: UUID, user_id: UUID) -> EventResponse | None:
        return await self.session.scalar(
            select(EventResponse).where(
                EventResponse.event_id == event_id,
                EventResponse.user_id == user_id,
            )
        )

    async def interested_user_ids(self, event_id: UUID) -> list[UUID]:
        result = await self.session.scalars(
            select(EventResponse.user_id).where(
                EventResponse.event_id == event_id,
                EventResponse.response.in_([ResponseType.GOING, ResponseType.LATER]),
            )
        )
        return list(result)
