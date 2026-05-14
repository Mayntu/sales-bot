import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base_repo import AbstractRepository
from app.domain.conversations.models import Message, MessageRole


class ConversationsRepo(AbstractRepository[Message]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, id: uuid.UUID) -> Message | None:
        res = await self.db.execute(select(Message).where(Message.id == id))
        return res.scalars().first()

    async def add_message(self, user_id: uuid.UUID, role: MessageRole, content: str) -> None:
        self.db.add(Message(user_id=user_id, role=role, content=content))

    async def last_messages(self, user_id: uuid.UUID, limit: int) -> list[Message]:
        res = await self.db.execute(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = list(res.scalars().all())
        rows.reverse()
        return rows
