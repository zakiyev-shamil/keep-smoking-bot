from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EventStatus, EventType
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_type

if TYPE_CHECKING:
    from app.models.event_poll_option import EventPollOption
    from app.models.event_response import EventResponse
    from app.models.party import Party
    from app.models.user import User


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_party_status", "party_id", "status"),
        Index("ix_events_party_type_created", "party_id", "type", "created_at"),
        Index("ix_events_expires_at", "expires_at"),
        Index(
            "uq_events_active_party_type",
            "party_id",
            "type",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    party_id: Mapped[UUID] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[EventType] = mapped_column(enum_type(EventType, "event_type"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EventStatus] = mapped_column(
        enum_type(EventStatus, "event_status"),
        default=EventStatus.ACTIVE,
        server_default=EventStatus.ACTIVE.value,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creator_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    creator_message_id: Mapped[int | None] = mapped_column(BigInteger)

    party: Mapped[Party] = relationship(back_populates="events")
    creator: Mapped[User] = relationship(foreign_keys=[creator_id])
    responses: Mapped[list[EventResponse]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    poll_options: Mapped[list[EventPollOption]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventPollOption.position",
    )
