from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class SystemConfigBase(BaseModel):
    key: str
    value: str
    version: str = "1.0"
    description: Optional[str] = None
    is_public: bool = False

class SystemConfigCreate(SystemConfigBase):
    pass

class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None

class SystemConfigResponse(SystemConfigBase):
    updated_at: datetime

    class Config:
        from_attributes = True
