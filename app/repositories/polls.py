from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_poll_option import EventPollOption
from app.models.event_poll_vote import EventPollVote


class EventPollRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_options(
        self,
        event_id: UUID,
        options: Sequence[str],
    ) -> list[EventPollOption]:
        result = [
            EventPollOption(event_id=event_id, text=text, position=position)
            for position, text in enumerate(options)
        ]
        self.session.add_all(result)
        await self.session.flush()
        return result

    async def option(self, event_id: UUID, option_id: UUID) -> EventPollOption | None:
        return await self.session.scalar(
            select(EventPollOption).where(
                EventPollOption.event_id == event_id,
                EventPollOption.id == option_id,
            )
        )

    async def options_with_counts(
        self,
        event_id: UUID,
    ) -> list[tuple[EventPollOption, int]]:
        rows = (
            await self.session.execute(
                select(EventPollOption, func.count(EventPollVote.id))
                .outerjoin(
                    EventPollVote,
                    (EventPollVote.event_id == EventPollOption.event_id)
                    & (EventPollVote.option_id == EventPollOption.id),
                )
                .where(EventPollOption.event_id == event_id)
                .group_by(EventPollOption.id)
                .order_by(EventPollOption.position)
            )
        ).all()
        return [(option, int(count)) for option, count in rows]

    async def selected_option_id(self, event_id: UUID, user_id: UUID) -> UUID | None:
        return await self.session.scalar(
            select(EventPollVote.option_id).where(
                EventPollVote.event_id == event_id,
                EventPollVote.user_id == user_id,
            )
        )

    async def upsert_vote(self, event_id: UUID, user_id: UUID, option_id: UUID) -> None:
        values = {
            "event_id": event_id,
            "user_id": user_id,
            "option_id": option_id,
        }
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            statement = postgresql_insert(EventPollVote).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[EventPollVote.event_id, EventPollVote.user_id],
                set_={"option_id": option_id, "updated_at": func.now()},
            )
            await self.session.execute(statement)
        elif bind.dialect.name == "sqlite":
            statement = sqlite_insert(EventPollVote).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[EventPollVote.event_id, EventPollVote.user_id],
                set_={"option_id": option_id, "updated_at": func.now()},
            )
            await self.session.execute(statement)
        else:
            vote = await self.session.scalar(
                select(EventPollVote).where(
                    EventPollVote.event_id == event_id,
                    EventPollVote.user_id == user_id,
                )
            )
            if vote is None:
                self.session.add(EventPollVote(**values))
            else:
                vote.option_id = option_id
        await self.session.flush()

    async def clear_vote(self, event_id: UUID, user_id: UUID) -> None:
        await self.session.execute(
            delete(EventPollVote).where(
                EventPollVote.event_id == event_id,
                EventPollVote.user_id == user_id,
            )
        )
