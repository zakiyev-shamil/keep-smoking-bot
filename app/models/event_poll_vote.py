from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.event_poll_option import EventPollOption
    from app.models.user import User


class EventPollVote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "event_poll_votes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "option_id"],
            ["event_poll_options.event_id", "event_poll_options.id"],
            name="fk_event_poll_votes_event_option",
            ondelete="CASCADE",
        ),
        UniqueConstraint("event_id", "user_id", name="uq_event_poll_votes_event_user"),
    )

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        index=True,
    )
    option_id: Mapped[UUID] = mapped_column(index=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    event: Mapped[Event] = relationship(foreign_keys=[event_id], overlaps="option,votes")
    option: Mapped[EventPollOption] = relationship(
        back_populates="votes",
        foreign_keys=[event_id, option_id],
        overlaps="event",
    )
    user: Mapped[User] = relationship()
