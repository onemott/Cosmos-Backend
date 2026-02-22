"""Bank data synchronization tasks."""

import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import delete, select

from src.workers.celery_app import celery_app
from src.core.logging import get_logger
from src.core.config import settings
from src.db.session import async_session_factory
from src.models.audit_log import AuditLog, AuditLogArchive

logger = get_logger(__name__)


@celery_app.task(bind=True)
def sync_bank_connection(self, connection_id: str) -> dict:
    """Sync data for a single bank connection."""
    logger.info(f"Starting sync for bank connection: {connection_id}")
    # TODO: Implement bank connection sync
    return {"status": "completed", "connection_id": connection_id}


@celery_app.task(bind=True)
def sync_all_bank_connections(self) -> dict:
    """Sync data for all active bank connections."""
    logger.info("Starting sync for all bank connections")
    # TODO: Implement full sync
    return {"status": "completed", "connections_synced": 0}


@celery_app.task(bind=True)
def sync_tenant_data(self, tenant_id: str) -> dict:
    """Sync all data for a specific tenant."""
    logger.info(f"Starting sync for tenant: {tenant_id}")
    # TODO: Implement tenant data sync
    return {"status": "completed", "tenant_id": tenant_id}


async def _archive_audit_logs() -> dict:
    archived_count = 0
    batch_size = settings.audit_log_archive_batch_size
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_log_archive_after_days)
    delete_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_log_retention_days)

    async with async_session_factory() as session:
        while True:
            query = (
                select(AuditLog)
                .where(AuditLog.created_at < cutoff)
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
                .limit(batch_size)
            )
            result = await session.execute(query)
            logs = result.scalars().all()
            if not logs:
                break

            archive_items = [
                AuditLogArchive(
                    id=log.id,
                    tenant_id=log.tenant_id,
                    event_type=log.event_type,
                    level=log.level,
                    category=log.category,
                    resource_type=log.resource_type,
                    resource_id=log.resource_id,
                    action=log.action,
                    outcome=log.outcome,
                    user_id=log.user_id,
                    user_email=log.user_email,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                    request_id=log.request_id,
                    event_hash=log.event_hash,
                    prev_hash=log.prev_hash,
                    old_value=log.old_value,
                    new_value=log.new_value,
                    extra_data=log.extra_data,
                    tags=log.tags,
                    created_at=log.created_at,
                )
                for log in logs
            ]
            session.add_all(archive_items)
            for log in logs:
                await session.delete(log)
            await session.commit()
            archived_count += len(logs)

        await session.execute(delete(AuditLogArchive).where(AuditLogArchive.created_at < delete_cutoff))
        await session.commit()

    return {"status": "completed", "archived": archived_count}


@celery_app.task(bind=True)
def archive_audit_logs(self) -> dict:
    """Archive old audit logs and enforce retention policy."""
    logger.info("Starting audit log archive task")
    return asyncio.run(_archive_audit_logs())

