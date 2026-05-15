"""Widen follow_up_tasks.message_type for 3d / 14d (was VARCHAR(2))

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Было VARCHAR(2) под 2h/5h/1d/7d — не влезают 3d и 14d
    op.execute(
        sa.text(
            "ALTER TABLE follow_up_tasks "
            "ALTER COLUMN message_type TYPE VARCHAR(16) "
            "USING message_type::text"
        )
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
    op.execute(
        sa.text(
            "ALTER TABLE follow_up_tasks "
            "ALTER COLUMN message_type TYPE VARCHAR(2) "
            "USING LEFT(message_type::text, 2)"
        )
    )
