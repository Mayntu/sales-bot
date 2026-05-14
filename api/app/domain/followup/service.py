from app.domain.followup.repo import FollowUpRepo
from app.domain.users.models import UserState


class FollowUpService:
    def __init__(self, repo: FollowUpRepo):
        self.repo = repo

    async def reschedule(self, user):
        await self.repo.cancel_pending(user.id)
        if user.state in (UserState.PAID, UserState.DEAD, UserState.CLOSE, UserState.WAITING_PAYMENT):
            return []
        return await self.repo.create_chain(user)
