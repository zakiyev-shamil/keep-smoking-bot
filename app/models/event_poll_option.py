from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.event_poll_vote import EventPollVote


class EventPollOption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "event_poll_options"
    __table_args__ = (
        UniqueConstraint("event_id", "position", name="uq_event_poll_options_event_position"),
        UniqueConstraint("event_id", "id", name="uq_event_poll_options_event_id"),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
    )
    text: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)

    event: Mapped[Event] = relationship(back_populates="poll_options")
    votes: Mapped[list[EventPollVote]] = relationship(
        back_populates="option",
        cascade="all, delete-orphan",
        foreign_keys="[EventPollVote.event_id, EventPollVote.option_id]",
        overlaps="event",
    )
