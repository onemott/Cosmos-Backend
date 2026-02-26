"""User Agreement model."""

from typing import Optional, TYPE_CHECKING
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UUID

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.client_user import ClientUser

class UserAgreement(Base):
    """User agreement acceptance record."""
    __tablename__ = "user_agreements"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # User who accepted the agreement (either staff or client)
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True
    )
    client_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("client_users.id"), nullable=True, index=True
    )
    
    # Agreement details
    agreement_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # e.g. privacy_policy
    version: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. "1.0"
    
    # Audit info
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_info: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", backref="agreements")
    client_user: Mapped[Optional["ClientUser"]] = relationship("ClientUser", backref="agreements")
