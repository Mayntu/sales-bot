import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base_repo import AbstractRepository
from app.domain.followup.models import FollowUpMessageType, FollowUpStatus, FollowUpTask
from app.domain.users.models import User

_FOLLOWUP_SCHEDULE: list[tuple[timedelta, FollowUpMessageType]] = [
    (timedelta(hours=2), FollowUpMessageType.h2),
    (timedelta(hours=5), FollowUpMessageType.h5),
    (timedelta(days=1), FollowUpMessageType.d1),
    (timedelta(days=3), FollowUpMessageType.d3),
    (timedelta(days=7), FollowUpMessageType.d7),
    (timedelta(days=14), FollowUpMessageType.d14),
]


class FollowUpRepo(AbstractRepository[FollowUpTask]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, id: uuid.UUID) -> FollowUpTask | None:
        res = await self.db.execute(select(FollowUpTask).where(FollowUpTask.id == id))
        return res.scalars().first()

    async def cancel_pending(self, user_id: uuid.UUID) -> None:
        # Revoke ETA tasks that are still waiting in the Celery broker (Redis)
        # so they don't wake up and do a pointless DB round-trip.
        res = await self.db.execute(
            select(FollowUpTask).where(
                FollowUpTask.user_id == user_id,
                FollowUpTask.status == FollowUpStatus.pending,
            )
        )
        pending = res.scalars().all()
        if pending:
            from app.tasks.celery_app import celery_app  # avoid circular at module level

            for task in pending:
                if task.celery_task_id:
                    celery_app.control.revoke(task.celery_task_id, terminate=False)

            await self.db.execute(
                update(FollowUpTask)
                .where(FollowUpTask.user_id == user_id, FollowUpTask.status == FollowUpStatus.pending)
                .values(status=FollowUpStatus.cancelled)
            )

    async def create_chain(self, user: User) -> list[FollowUpTask]:
        baseline = user.last_message_at
        if baseline.tzinfo is None:
            baseline = baseline.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        tasks: list[FollowUpTask] = []
        for delta, mtype in _FOLLOWUP_SCHEDULE:
            task = FollowUpTask(
                user_id=user.id,
                scheduled_at=now + delta,
                message_type=mtype,
                baseline_last_message_at=baseline,
            )
            self.db.add(task)
            tasks.append(task)

        await self.db.flush()
        return tasks

    async def get_next_pending_ordered(self, user_id: uuid.UUID) -> FollowUpTask | None:
        res = await self.db.execute(
            select(FollowUpTask)
            .where(
                FollowUpTask.user_id == user_id,
                FollowUpTask.status == FollowUpStatus.pending,
            )
            .order_by(FollowUpTask.scheduled_at.asc())
            .limit(1)
        )
        return res.scalars().first()

    async def revoke_celery_for_task(self, task: FollowUpTask) -> None:
        if not task.celery_task_id:
            return
        from app.tasks.celery_app import celery_app

        celery_app.control.revoke(task.celery_task_id, terminate=False)
