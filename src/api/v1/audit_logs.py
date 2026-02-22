from datetime import datetime
from typing import Optional, Iterable, Dict, Any
import csv
import io

from fastapi import APIRouter, Depends, Query, Request, status, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_tenant_admin, get_current_user, is_platform_admin, get_user_role_level
from src.db.session import get_db
from src.db.repositories.audit_log_repo import AuditLogRepository
from src.db.repositories.user_repo import UserRepository
from src.schemas.audit_log import (
    AuditLogCreateRequest,
    AuditLogResponse,
    AuditLogListResponse,
    AuditLogSummaryResponse,
    AuditLogSummaryItem,
)
from src.services.audit_log_service import AuditLogService, build_request_context

router = APIRouter()


@router.get("/", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    event_type: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    user_email: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    ip_address: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AuditLogListResponse:
    repo = AuditLogRepository(db)
    role_level = get_user_role_level(current_user)
    if tenant_id and role_level not in {"platform_admin", "platform_user"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    user_ids = None
    if role_level == "platform_admin":
        tenant_scope = tenant_id
    elif role_level == "platform_user":
        tenant_scope = tenant_id
    elif role_level == "tenant_admin":
        tenant_scope = current_user.get("tenant_id")
    elif role_level == "eam_supervisor":
        tenant_scope = current_user.get("tenant_id")
        user_repo = UserRepository(db)
        team_ids = await user_repo.get_team_scope_user_ids(current_user.get("user_id"))
        if user_id and user_id not in team_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        user_ids = team_ids if not user_id else [user_id]
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    items, total = await repo.list_logs(
        tenant_id=tenant_scope,
        skip=skip,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
        level=level,
        category=category,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        user_ids=user_ids,
        user_email=user_email,
        request_id=request_id,
        ip_address=ip_address,
        outcome=outcome,
        search=search,
    )
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )


@router.get("/summary", response_model=AuditLogSummaryResponse)
async def audit_log_summary(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    tenant_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AuditLogSummaryResponse:
    repo = AuditLogRepository(db)
    role_level = get_user_role_level(current_user)
    if tenant_id and role_level not in {"platform_admin", "platform_user"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    user_ids = None
    if role_level == "platform_admin":
        tenant_scope = tenant_id
    elif role_level == "platform_user":
        tenant_scope = tenant_id
    elif role_level == "tenant_admin":
        tenant_scope = current_user.get("tenant_id")
    elif role_level == "eam_supervisor":
        tenant_scope = current_user.get("tenant_id")
        user_repo = UserRepository(db)
        user_ids = await user_repo.get_team_scope_user_ids(current_user.get("user_id"))
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    summary = await repo.summary(
        tenant_scope,
        start_time=start_time,
        end_time=end_time,
        user_ids=user_ids,
    )
    return AuditLogSummaryResponse(
        total=summary["total"],
        by_event_type=[
            AuditLogSummaryItem(key=key or "unknown", count=count)
            for key, count in summary["by_event_type"]
        ],
        by_level=[
            AuditLogSummaryItem(key=key or "unknown", count=count)
            for key, count in summary["by_level"]
        ],
        by_outcome=[
            AuditLogSummaryItem(key=key or "unknown", count=count)
            for key, count in summary["by_outcome"]
        ],
        range_start=start_time,
        range_end=end_time,
    )


@router.post("/", response_model=AuditLogResponse, status_code=status.HTTP_201_CREATED)
async def create_audit_log(
    payload: AuditLogCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_tenant_admin),
) -> AuditLogResponse:
    tenant_id = payload.tenant_id if is_platform_admin(current_user) and payload.tenant_id else current_user.get("tenant_id")
    context = build_request_context(request)
    service = AuditLogService(db)
    log = await service.create_log(
        {
            **payload.model_dump(exclude={"tenant_id"}),
            "tenant_id": tenant_id,
            "user_id": current_user.get("user_id"),
            "user_email": current_user.get("email"),
            **context,
        }
    )
    await db.commit()
    return AuditLogResponse.model_validate(log)


@router.get("/export")
async def export_audit_logs(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    event_type: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    user_email: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    ip_address: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    repo = AuditLogRepository(db)
    role_level = get_user_role_level(current_user)
    if tenant_id and role_level not in {"platform_admin", "platform_user"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    user_ids = None
    if role_level == "platform_admin":
        tenant_scope = tenant_id
    elif role_level == "platform_user":
        tenant_scope = tenant_id
    elif role_level == "tenant_admin":
        tenant_scope = current_user.get("tenant_id")
    elif role_level == "eam_supervisor":
        tenant_scope = current_user.get("tenant_id")
        user_repo = UserRepository(db)
        team_ids = await user_repo.get_team_scope_user_ids(current_user.get("user_id"))
        if user_id and user_id not in team_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        user_ids = team_ids if not user_id else [user_id]
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    items, _ = await repo.list_logs(
        tenant_id=tenant_scope,
        skip=0,
        limit=5000,
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
        level=level,
        category=category,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        user_ids=user_ids,
        user_email=user_email,
        request_id=request_id,
        ip_address=ip_address,
        outcome=outcome,
        search=search,
    )

    def stream() -> Iterable[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "tenant_id",
                "event_type",
                "level",
                "category",
                "resource_type",
                "resource_id",
                "action",
                "outcome",
                "user_id",
                "user_email",
                "ip_address",
                "user_agent",
                "request_id",
                "created_at",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for item in items:
            writer.writerow(
                [
                    item.id,
                    item.tenant_id,
                    item.event_type,
                    item.level,
                    item.category,
                    item.resource_type,
                    item.resource_id,
                    item.action,
                    item.outcome,
                    item.user_id,
                    item.user_email,
                    item.ip_address,
                    item.user_agent,
                    item.request_id,
                    item.created_at.isoformat(),
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    filename = f"audit_logs_{datetime.utcnow().date().isoformat()}.csv"
    response = StreamingResponse(stream(), media_type="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
