"""follow_up_tasks: allow message_type 3d and 14d

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_message_types() -> None:
    """Привести message_type к канону до CHECK: любые левые/stale строки после create_all без alembic."""
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE follow_up_tasks
            SET message_type =
                CASE btrim(lower(coalesce(message_type::text, '')))
                    WHEN '2h' THEN '2h'
                    WHEN '5h' THEN '5h'
                    WHEN '1d' THEN '1d'
                    WHEN '3d' THEN '3d'
                    WHEN '7d' THEN '7d'
                    WHEN '14d' THEN '14d'
                    ELSE '7d'
                END;
            """
        )
    )


def _drop_message_type_checks() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT c.conname
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            WHERE t.relname = 'follow_up_tasks'
              AND c.contype = 'c'
              AND pg_get_constraintdef(c.oid) ILIKE '%message_type%';
            """
        )
    ).fetchall()
    for (name,) in rows:
        op.drop_constraint(name, "follow_up_tasks", type_="check")


def upgrade() -> None:
    _drop_message_type_checks()
    _normalize_message_types()
    op.create_check_constraint(
        "ck_follow_up_tasks_message_type",
        "follow_up_tasks",
        "message_type IN ('2h','5h','1d','3d','7d','14d')",
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM follow_up_tasks
            WHERE message_type IN ('3d', '14d');
            """
        )
    )
    _drop_message_type_checks()
    op.create_check_constraint(
        "ck_follow_up_tasks_message_type",
        "follow_up_tasks",
        "message_type IN ('2h','5h','1d','7d')",
    )
