from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class BotFsmState(TimestampMixin, Base):
    __tablename__ = "bot_fsm_states"

    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        nullable=False,
    )
