"""store bot runtime state in PostgreSQL

Revision ID: 20260718_02
Revises: 20260718_01
Create Date: 2026-07-18 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_02"
down_revision: str | None = "20260718_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_fsm_states",
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
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
        sa.PrimaryKeyConstraint("key", name=op.f("pk_bot_fsm_states")),
    )
    op.create_table(
        "user_runtime_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("active_party_id", sa.Uuid(), nullable=True),
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
            ["active_party_id"],
            ["parties.id"],
            name=op.f("fk_user_runtime_states_active_party_id_parties"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_runtime_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_runtime_states")),
    )
    op.create_index(
        op.f("ix_user_runtime_states_active_party_id"),
        "user_runtime_states",
        ["active_party_id"],
        unique=False,
    )
    op.add_column("events", sa.Column("creator_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("events", sa.Column("creator_message_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "creator_message_id")
    op.drop_column("events", "creator_chat_id")
    op.drop_table("user_runtime_states")
    op.drop_table("bot_fsm_states")
