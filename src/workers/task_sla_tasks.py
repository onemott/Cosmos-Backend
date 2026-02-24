import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func

from src.workers.celery_app import celery_app
from src.core.logging import get_logger
from src.core.config import settings
from src.db.session import async_session_factory
from src.models.task import (
    Task,
    TaskStatus,
    WorkflowState,
    TaskPriority,
    TaskMessage,
    TaskMessageAuthorType,
)
from src.models.user import User

logger = get_logger(__name__)


async def _create_system_message(session, task: Task, body: str) -> None:
    max_version_result = await session.execute(
        select(func.max(TaskMessage.version)).where(TaskMessage.task_id == task.id)
    )
    version = (max_version_result.scalar() or 0) + 1
    message = TaskMessage(
        tenant_id=task.tenant_id,
        task_id=task.id,
        client_id=task.client_id,
        author_type=TaskMessageAuthorType.SYSTEM,
        body=body,
        version=version,
    )
    session.add(message)


async def _process_task_sla() -> dict:
    now = datetime.now(timezone.utc)
    expired_count = 0
    escalated_count = 0

    async with async_session_factory() as session:
        expire_query = select(Task).where(
            Task.workflow_state == WorkflowState.PENDING_CLIENT,
            Task.status == TaskStatus.PENDING,
            Task.approval_required_by.is_not(None),
            Task.approval_required_by < now,
        )
        expire_result = await session.execute(expire_query)
        expired_tasks = expire_result.scalars().all()

        for task in expired_tasks:
            task.workflow_state = WorkflowState.EXPIRED
            task.status = TaskStatus.ON_HOLD
            await _create_system_message(session, task, "任务已超时，等待客户审批已过期")
            expired_count += 1

        escalation_cooldown = timedelta(
            hours=settings.task_sla_escalation_cooldown_hours
        )
        overdue_query = select(Task).where(
            Task.due_date.is_not(None),
            Task.due_date < now,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            Task.assigned_to_id.is_not(None),
            Task.workflow_state != WorkflowState.PENDING_CLIENT,
            Task.escalation_level < settings.task_sla_max_escalation_level,
        )
        overdue_result = await session.execute(overdue_query)
        overdue_tasks = overdue_result.scalars().all()

        if overdue_tasks:
            assigned_ids = {t.assigned_to_id for t in overdue_tasks if t.assigned_to_id}
            users_result = await session.execute(
                select(User.id, User.supervisor_id).where(User.id.in_(list(assigned_ids)))
            )
            supervisor_map = {str(u.id): u.supervisor_id for u in users_result.all()}

            for task in overdue_tasks:
                if task.escalated_at and (now - task.escalated_at) < escalation_cooldown:
                    continue
                supervisor_id = supervisor_map.get(str(task.assigned_to_id))
                if not supervisor_id:
                    continue
                task.assigned_to_id = supervisor_id
                task.escalated_to_id = supervisor_id
                task.escalated_at = now
                task.escalation_level = (task.escalation_level or 0) + 1
                if task.priority != TaskPriority.URGENT:
                    task.priority = TaskPriority.URGENT
                await _create_system_message(session, task, "任务超时，已自动升级给上级处理")
                escalated_count += 1

        await session.commit()

    return {
        "status": "completed",
        "expired": expired_count,
        "escalated": escalated_count,
    }


@celery_app.task(bind=True)
def process_task_sla(self) -> dict:
    logger.info("Processing task SLA")
    return asyncio.run(_process_task_sla())
