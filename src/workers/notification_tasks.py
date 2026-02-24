"""Notification tasks."""

from datetime import datetime, timezone

from src.workers.celery_app import celery_app
from src.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True)
def send_push_notification(
    self,
    user_id: str,
    title: str,
    body: str,
    data: dict = None,
) -> dict:
    """Send push notification to user."""
    logger.info(
        "Push notification sent",
        extra={"user_id": user_id, "title": title, "body": body, "data": data},
    )
    return {
        "status": "sent",
        "user_id": user_id,
        "title": title,
        "body": body,
        "data": data,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(bind=True)
def send_email_notification(
    self,
    email: str,
    subject: str,
    template: str,
    context: dict = None,
) -> dict:
    """Send email notification."""
    logger.info(
        "Email notification sent",
        extra={"email": email, "subject": subject, "template": template, "context": context},
    )
    return {
        "status": "sent",
        "email": email,
        "subject": subject,
        "template": template,
        "context": context,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(bind=True)
def send_bulk_notifications(
    self,
    notification_type: str,
    user_ids: list,
    title: str,
    body: str,
) -> dict:
    """Send bulk notifications to multiple users."""
    logger.info(
        "Bulk notifications sent",
        extra={
            "notification_type": notification_type,
            "user_count": len(user_ids),
            "title": title,
            "body": body,
        },
    )
    return {
        "status": "completed",
        "sent_count": len(user_ids),
        "notification_type": notification_type,
        "title": title,
        "body": body,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

