from datetime import datetime
from typing import Optional, List, Tuple, TypedDict

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog


class AuditLogSummary(TypedDict):
    total: int
    by_event_type: List[Tuple[Optional[str], int]]
    by_level: List[Tuple[Optional[str], int]]
    by_outcome: List[Tuple[Optional[str], int]]


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        tenant_id: Optional[str],
        skip: int,
        limit: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        category: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_ids: Optional[List[str]] = None,
        user_email: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        outcome: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        filters = []
        if tenant_id is not None:
            filters.append(AuditLog.tenant_id == tenant_id)
        if start_time:
            filters.append(AuditLog.created_at >= start_time)
        if end_time:
            filters.append(AuditLog.created_at <= end_time)
        if event_type:
            filters.append(AuditLog.event_type == event_type)
        if level:
            filters.append(AuditLog.level == level)
        if category:
            filters.append(AuditLog.category == category)
        if action:
            filters.append(AuditLog.action == action)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            filters.append(AuditLog.resource_id == resource_id)
        if user_id:
            filters.append(AuditLog.user_id == user_id)
        if user_ids:
            filters.append(AuditLog.user_id.in_(user_ids))
        if user_email:
            filters.append(AuditLog.user_email == user_email)
        if request_id:
            filters.append(AuditLog.request_id == request_id)
        if ip_address:
            filters.append(AuditLog.ip_address == ip_address)
        if outcome:
            filters.append(AuditLog.outcome == outcome)
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    AuditLog.event_type.ilike(pattern),
                    AuditLog.resource_type.ilike(pattern),
                    AuditLog.action.ilike(pattern),
                    AuditLog.user_email.ilike(pattern),
                    AuditLog.ip_address.ilike(pattern),
                    AuditLog.request_id.ilike(pattern),
                    AuditLog.resource_id.ilike(pattern),
                )
            )

        query = select(AuditLog).where(and_(*filters)) if filters else select(AuditLog)
        count_query = (
            select(func.count())
            .select_from(AuditLog)
            .where(and_(*filters))
            if filters
            else select(func.count()).select_from(AuditLog)
        )

        query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        items = result.scalars().all()

        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        return items, total

    async def summary(
        self,
        tenant_id: Optional[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_ids: Optional[List[str]] = None,
    ) -> AuditLogSummary:
        filters = []
        if tenant_id is not None:
            filters.append(AuditLog.tenant_id == tenant_id)
        if start_time:
            filters.append(AuditLog.created_at >= start_time)
        if end_time:
            filters.append(AuditLog.created_at <= end_time)
        if user_ids:
            filters.append(AuditLog.user_id.in_(user_ids))

        base = select(AuditLog)
        if filters:
            base = base.where(and_(*filters))

        total_query = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(total_query)
        total = total_result.scalar_one()

        by_event_type_query = (
            select(AuditLog.event_type, func.count())
            .where(and_(*filters)) if filters else select(AuditLog.event_type, func.count())
        )
        by_event_type_query = by_event_type_query.group_by(AuditLog.event_type)

        by_level_query = (
            select(AuditLog.level, func.count())
            .where(and_(*filters)) if filters else select(AuditLog.level, func.count())
        )
        by_level_query = by_level_query.group_by(AuditLog.level)

        by_outcome_query = (
            select(AuditLog.outcome, func.count())
            .where(and_(*filters)) if filters else select(AuditLog.outcome, func.count())
        )
        by_outcome_query = by_outcome_query.group_by(AuditLog.outcome)

        event_type_rows = (await self.session.execute(by_event_type_query)).all()
        level_rows = (await self.session.execute(by_level_query)).all()
        outcome_rows = (await self.session.execute(by_outcome_query)).all()

        return {
            "total": total,
            "by_event_type": event_type_rows,
            "by_level": level_rows,
            "by_outcome": outcome_rows,
        }
