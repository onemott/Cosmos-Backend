"""Celery application configuration."""

from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "eam_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.workers.sync_tasks",
        "src.workers.report_tasks",
        "src.workers.notification_tasks",
        "src.workers.task_sla_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    worker_prefetch_multiplier=1,
)

# Schedule periodic tasks
celery_app.conf.beat_schedule = {
    "sync-bank-data-daily": {
        "task": "src.workers.sync_tasks.sync_all_bank_connections",
        "schedule": 86400.0,  # Every 24 hours
    },
    "archive-audit-logs-daily": {
        "task": "src.workers.sync_tasks.archive_audit_logs",
        "schedule": 86400.0,
    },
    "process-task-sla": {
        "task": "src.workers.task_sla_tasks.process_task_sla",
        "schedule": settings.task_sla_interval_seconds,
    },
}

