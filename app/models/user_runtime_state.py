from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserRuntimeState(TimestampMixin, Base):
    __tablename__ = "user_runtime_states"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    active_party_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL"),
        index=True,
    )

    user: Mapped[User] = relationship(back_populates="runtime_state")
