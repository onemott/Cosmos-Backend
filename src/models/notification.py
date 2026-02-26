"""Notification model."""

from typing import Optional, TYPE_CHECKING
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, ForeignKey, Text, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUID

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.client_user import ClientUser

class Notification(Base):
    """Notification model."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Recipient (either staff user or client user)
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True
    )
    client_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("client_users.id"), nullable=True, index=True
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(20), default="text")  # text, markdown, html
    type: Mapped[str] = mapped_column(String(50), default="system", index=True)  # system, alert, promotion
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    
    # Optional metadata for deep linking or extra info
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) 

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", backref="notifications")
    client_user: Mapped[Optional["ClientUser"]] = relationship("ClientUser", backref="notifications")
