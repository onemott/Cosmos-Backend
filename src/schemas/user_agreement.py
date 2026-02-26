"""Schemas for user agreement management."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class UserAgreementBase(BaseModel):
    agreement_type: str = Field(..., max_length=50)
    version: str = Field(..., max_length=50)
    user_agent: Optional[str] = None
    device_info: Optional[str] = None

class UserAgreementCreate(UserAgreementBase):
    pass

class UserAgreementResponse(UserAgreementBase):
    id: str
    user_id: Optional[str] = None
    client_user_id: Optional[str] = None
    accepted_at: datetime
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True

class AgreementStatus(BaseModel):
    accepted: bool
    version: Optional[str] = None
    latest_version: Optional[str] = None
