from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "priceradar",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.parsing",
        "app.tasks.alerts",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Rate limiting
    task_default_rate_limit="10/m",
)

celery_app.conf.beat_schedule = {
    "parse-all-active-products": {
        "task": "app.tasks.parsing.parse_all_products",
        "schedule": crontab(minute="*/30"),
    },
    "check-alerts": {
        "task": "app.tasks.alerts.check_all_alerts",
        "schedule": crontab(minute="*/5"),
    },
    "cleanup-old-prices": {
        "task": "app.tasks.parsing.cleanup_old_prices",
        "schedule": crontab(hour=3, minute=0),
    },
    "deactivate-broken-products": {
        "task": "app.tasks.parsing.deactivate_broken",
        "schedule": crontab(hour=4, minute=0),
    },
}
