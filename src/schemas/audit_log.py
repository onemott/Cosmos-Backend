from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class AuditLogBase(BaseModel):
    event_type: str
    level: str = "info"
    category: str = "system"
    resource_type: str
    resource_id: Optional[str] = None
    action: str
    outcome: str = "success"
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    extra_data: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class AuditLogCreateRequest(AuditLogBase):
    tenant_id: Optional[str] = None


class AuditLogResponse(AuditLogBase):
    id: str
    tenant_id: str
    event_hash: Optional[str] = None
    prev_hash: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class AuditLogSummaryItem(BaseModel):
    key: str
    count: int


class AuditLogSummaryResponse(BaseModel):
    total: int
    by_event_type: List[AuditLogSummaryItem]
    by_level: List[AuditLogSummaryItem]
    by_outcome: List[AuditLogSummaryItem]
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None
