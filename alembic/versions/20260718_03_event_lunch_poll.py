"""add aggregated lunch event polls

Revision ID: 20260718_03
Revises: 20260718_02
Create Date: 2026-07-18 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_03"
down_revision: str | None = "20260718_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_poll_options",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_poll_options_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_poll_options")),
        sa.UniqueConstraint(
            "event_id",
            "id",
            name="uq_event_poll_options_event_id",
        ),
        sa.UniqueConstraint(
            "event_id",
            "position",
            name="uq_event_poll_options_event_position",
        ),
    )
    op.create_index(
        op.f("ix_event_poll_options_event_id"),
        "event_poll_options",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "event_poll_votes",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("option_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_poll_votes_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "option_id"],
            ["event_poll_options.event_id", "event_poll_options.id"],
            name="fk_event_poll_votes_event_option",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_event_poll_votes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_poll_votes")),
        sa.UniqueConstraint(
            "event_id",
            "user_id",
            name="uq_event_poll_votes_event_user",
        ),
    )
    op.create_index(
        op.f("ix_event_poll_votes_event_id"),
        "event_poll_votes",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_poll_votes_option_id"),
        "event_poll_votes",
        ["option_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_poll_votes_user_id"),
        "event_poll_votes",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("event_poll_votes")
    op.drop_table("event_poll_options")
