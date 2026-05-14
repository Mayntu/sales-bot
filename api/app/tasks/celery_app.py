from celery import Celery

from app.core.config import get_settings
from app.core.logger import configure_logging

configure_logging()

settings = get_settings()

celery_app = Celery(
    "gym-sales",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.followup",
        "app.tasks.notifications",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Separate queues for follow-up and Telegram notifications
    task_default_queue="followup",
    task_queues={
        "followup": {"exchange": "followup", "routing_key": "followup"},
        "notifications": {"exchange": "notifications", "routing_key": "notifications"},
    },
    beat_schedule={},
)
