from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PartyRole
from app.database.base import Base, UUIDPrimaryKeyMixin
from app.models._types import enum_type

if TYPE_CHECKING:
    from app.models.party import Party
    from app.models.user import User


class PartyMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "party_members"
    __table_args__ = (
        UniqueConstraint("party_id", "user_id", name="uq_party_members_party_user"),
        Index("ix_party_members_party_active", "party_id", "is_active"),
        Index("ix_party_members_user_active", "user_id", "is_active"),
    )

    party_id: Mapped[UUID] = mapped_column(ForeignKey("parties.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[PartyRole] = mapped_column(
        enum_type(PartyRole, "party_role"),
        default=PartyRole.MEMBER,
        server_default=PartyRole.MEMBER.value,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    party: Mapped[Party] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")
