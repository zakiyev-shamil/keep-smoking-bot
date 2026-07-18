from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EventCreationPolicy
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_type

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.party_member import PartyMember
    from app.models.user import User


class Party(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "parties"

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    invite_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    event_creation_policy: Mapped[EventCreationPolicy] = mapped_column(
        enum_type(EventCreationPolicy, "event_creation_policy"),
        default=EventCreationPolicy.EVERYONE,
        server_default=EventCreationPolicy.EVERYONE.value,
    )

    owner: Mapped[User] = relationship(foreign_keys=[owner_id])
    members: Mapped[list[PartyMember]] = relationship(
        back_populates="party", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(back_populates="party")
