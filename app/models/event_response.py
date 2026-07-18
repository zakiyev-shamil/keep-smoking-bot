from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ResponseType
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_type

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class EventResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "event_responses"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_event_responses_event_user"),
        Index("ix_event_responses_event_response", "event_id", "response"),
    )

    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    response: Mapped[ResponseType] = mapped_column(enum_type(ResponseType, "event_response_type"))

    event: Mapped[Event] = relationship(back_populates="responses")
    user: Mapped[User] = relationship()
