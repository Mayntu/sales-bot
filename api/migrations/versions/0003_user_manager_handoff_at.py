"""users.manager_handoff_at — момент передачи лида менеджеру (первый CLOSE)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("manager_handoff_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Уже в воронке до миграции — считаем handoff по времени регистрации
    op.execute(
        """
        UPDATE users
        SET manager_handoff_at = created_at
        WHERE manager_handoff_at IS NULL
          AND state IN ('CLOSE', 'WAITING_PAYMENT', 'PAID')
        """
    )


def downgrade() -> None:
    op.drop_column("users", "manager_handoff_at")
