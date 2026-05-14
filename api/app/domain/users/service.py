from datetime import datetime, timezone
from app.domain.users.repo import UsersRepo


class UsersService:
    def __init__(self, repo: UsersRepo):
        self.repo = repo

    async def get_or_create(self, chat_id: int):
        user = await self.repo.get_by_chat_id(chat_id)
        if user:
            return user
        return await self.repo.create(chat_id)

    @staticmethod
    def touch(user) -> None:
        user.last_message_at = datetime.now(timezone.utc)
