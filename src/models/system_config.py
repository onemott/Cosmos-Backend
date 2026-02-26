"""System Config model."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base

class SystemConfig(Base):
    """System configuration model for storing global settings like Privacy Policy."""

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0")
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=func.now(),
    )
