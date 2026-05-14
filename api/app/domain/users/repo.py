import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base_repo import AbstractRepository
from app.domain.users.models import User


class UsersRepo(AbstractRepository[User]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, id: uuid.UUID) -> User | None:
        res = await self.db.execute(select(User).where(User.id == id))
        return res.scalars().first()

    async def get_by_chat_id(self, chat_id: int) -> User | None:
        res = await self.db.execute(select(User).where(User.telegram_chat_id == chat_id))
        return res.scalars().first()

    async def create(self, chat_id: int) -> User:
        user = User(telegram_chat_id=chat_id)
        self.db.add(user)
        await self.db.flush()
        return user
