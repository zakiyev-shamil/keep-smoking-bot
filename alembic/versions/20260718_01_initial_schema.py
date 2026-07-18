"""initial office party schema

Revision ID: 20260718_01
Revises:
Create Date: 2026-07-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("bot_accessible", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True)

    op.create_table(
        "parties",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("invite_code", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "event_creation_policy",
            sa.Enum("everyone", "admins_only", name="event_creation_policy", native_enum=False),
            server_default="everyone",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_parties_owner_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parties")),
    )
    op.create_index(op.f("ix_parties_invite_code"), "parties", ["invite_code"], unique=True)
    op.create_index(op.f("ix_parties_owner_id"), "parties", ["owner_id"], unique=False)

    op.create_table(
        "party_members",
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "member", name="party_role", native_enum=False),
            server_default="member",
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["party_id"],
            ["parties.id"],
            name=op.f("fk_party_members_party_id_parties"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_party_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_party_members")),
        sa.UniqueConstraint("party_id", "user_id", name="uq_party_members_party_user"),
    )
    op.create_index("ix_party_members_party_active", "party_members", ["party_id", "is_active"])
    op.create_index(op.f("ix_party_members_party_id"), "party_members", ["party_id"])
    op.create_index("ix_party_members_user_active", "party_members", ["user_id", "is_active"])
    op.create_index(op.f("ix_party_members_user_id"), "party_members", ["user_id"])

    op.create_table(
        "user_notification_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("smoke_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("coffee_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("lunch_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("after_work_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("custom_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("quiet_hours_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("quiet_from", sa.Time(), nullable=True),
        sa.Column("quiet_to", sa.Time(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("event_started_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("event_cancelled_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_notification_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_notification_settings")),
    )

    op.create_table(
        "events",
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "smoke",
                "coffee",
                "lunch",
                "after_work",
                "custom",
                name="event_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "started",
                "cancelled",
                "expired",
                name="event_status",
                native_enum=False,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
            name=op.f("fk_events_creator_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"],
            ["parties.id"],
            name=op.f("fk_events_party_id_parties"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_expires_at"), "events", ["expires_at"])
    op.create_index(op.f("ix_events_party_id"), "events", ["party_id"])
    op.create_index("ix_events_party_status", "events", ["party_id", "status"])
    op.create_index("ix_events_party_type_created", "events", ["party_id", "type", "created_at"])
    op.create_index(op.f("ix_events_status"), "events", ["status"])
    op.create_index(op.f("ix_events_type"), "events", ["type"])
    op.create_index(
        "uq_events_active_party_type",
        "events",
        ["party_id", "type"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "event_responses",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "response",
            sa.Enum(
                "going", "later", "declined", name="event_response_type", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_responses_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_event_responses_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_responses")),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_responses_event_user"),
    )
    op.create_index(op.f("ix_event_responses_event_id"), "event_responses", ["event_id"])
    op.create_index(
        "ix_event_responses_event_response", "event_responses", ["event_id", "response"]
    )
    op.create_index(op.f("ix_event_responses_user_id"), "event_responses", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sending",
                "sent",
                "failed",
                "blocked",
                name="notification_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_notifications_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("event_id", "recipient_id", name="uq_notifications_event_recipient"),
    )
    op.create_index(op.f("ix_notifications_event_id"), "notifications", ["event_id"])
    op.create_index(op.f("ix_notifications_recipient_id"), "notifications", ["recipient_id"])
    op.create_index(
        "ix_notifications_status_created", "notifications", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("event_responses")
    op.drop_table("events")
    op.drop_table("user_notification_settings")
    op.drop_table("party_members")
    op.drop_table("parties")
    op.drop_table("users")
