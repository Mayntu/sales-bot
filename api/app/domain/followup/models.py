import enum
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.domain.users.models import Base


class FollowUpMessageType(str, enum.Enum):
    h2 = '2h'
    h5 = '5h'
    d1 = '1d'
    d3 = '3d'
    d7 = '7d'
    d14 = '14d'


class FollowUpStatus(str, enum.Enum):
    pending = 'pending'
    sent = 'sent'
    cancelled = 'cancelled'


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Хранить в VARCHAR значения enum ('2h', '7d'), не имена членов ('h2', 'd7') — как в миграциях."""
    return [str(e.value) for e in enum_cls]


class FollowUpTask(Base):
    __tablename__ = 'follow_up_tasks'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_type: Mapped[FollowUpMessageType] = mapped_column(
        SAEnum(
            FollowUpMessageType,
            name='followup_message_type',
            native_enum=False,
            length=16,
            values_callable=_enum_values,
        )
    )
    status: Mapped[FollowUpStatus] = mapped_column(
        SAEnum(
            FollowUpStatus,
            name='followup_status',
            native_enum=False,
            length=16,
            values_callable=_enum_values,
        ),
        default=FollowUpStatus.pending,
    )
    baseline_last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Celery ETA task ID — used to revoke the broker-side task on cancellation
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
