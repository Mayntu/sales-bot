import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, Integer, String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pydantic import BaseModel


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserState(str, enum.Enum):
    NEW = 'NEW'
    QUALIFY = 'QUALIFY'
    PRESENT = 'PRESENT'
    HANDLE_OBJECTION = 'HANDLE_OBJECTION'
    CLOSE = 'CLOSE'
    WAITING_PAYMENT = 'WAITING_PAYMENT'
    PAID = 'PAID'
    DEAD = 'DEAD'


class User(Base):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[UserState] = mapped_column(SAEnum(UserState, name='user_state', native_enum=False), default=UserState.NEW, index=True)
    goal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UserOut(BaseModel):
    telegram_chat_id: int
    state: UserState
    name: str | None
    goal: str | None
