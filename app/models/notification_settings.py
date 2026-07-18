from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserNotificationSettings(TimestampMixin, Base):
    __tablename__ = "user_notification_settings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    smoke_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    coffee_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    lunch_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    after_work_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    custom_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    quiet_from: Mapped[time | None] = mapped_column(Time(timezone=False))
    quiet_to: Mapped[time | None] = mapped_column(Time(timezone=False))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Almaty")
    event_started_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    event_cancelled_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    user: Mapped[User] = relationship(back_populates="notification_settings")
