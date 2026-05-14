"""Initial schema — users, messages, follow_up_tasks

Revision ID: 0001
Revises:
Create Date: 2026-05-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "NEW", "QUALIFY", "PRESENT", "HANDLE_OBJECTION",
                "CLOSE", "WAITING_PAYMENT", "PAID", "DEAD",
                name="user_state",
                native_enum=False,
            ),
            nullable=False,
            server_default="NEW",
        ),
        sa.Column("goal", sa.String(255), nullable=True),
        sa.Column("followup_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_users_telegram_chat_id", "users", ["telegram_chat_id"], unique=True)
    op.create_index("ix_users_state", "users", ["state"])
    op.create_index("ix_users_last_message_at", "users", ["last_message_at"])

    # ── messages ──────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="message_role", native_enum=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])

    # ── follow_up_tasks ───────────────────────────────────────────────────────
    op.create_table(
        "follow_up_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "message_type",
            sa.Enum("2h", "5h", "1d", "7d", name="followup_message_type", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "cancelled", name="followup_status", native_enum=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("baseline_last_message_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_follow_up_tasks_user_id", "follow_up_tasks", ["user_id"])
    op.create_index("ix_follow_up_tasks_scheduled_at", "follow_up_tasks", ["scheduled_at"])


def downgrade() -> None:
    op.drop_table("follow_up_tasks")
    op.drop_table("messages")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS followup_status")
    op.execute("DROP TYPE IF EXISTS followup_message_type")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS user_state")
