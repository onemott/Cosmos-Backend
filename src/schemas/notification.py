"""Schemas for notification management."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class NotificationBase(BaseModel):
    title: str = Field(..., max_length=255)
    content: str
    content_format: str = Field(default="text", max_length=20)
    type: str = Field(default="system", max_length=50)
    metadata_json: Optional[dict] = None

class NotificationCreate(NotificationBase):
    user_id: Optional[str] = None
    client_user_id: Optional[str] = None

class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None

class NotificationResponse(NotificationBase):
    id: str
    user_id: Optional[str] = None
    client_user_id: Optional[str] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int
    skip: int
    limit: int

class NotificationSendRequest(NotificationBase):
    target_type: str = Field(..., pattern="^(user|tenant|all)$")
    target_id: Optional[str] = None # user_id or tenant_id
