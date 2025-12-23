"""ClientUser model for client authentication."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.client import Client
    from src.models.tenant import Tenant


class ClientUser(Base, TimestampMixin):
    """Client user model for client authentication.
    
    This is separate from the User model (staff/operators) to maintain
    separation of concerns between CRM data and authentication data.
    
    Relationship: Client 1:1 ClientUser (extensible to 1:many for family offices)
    """

    __tablename__ = "client_users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    
    # Foreign keys
    client_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        ForeignKey("clients.id"), 
        nullable=False, 
        unique=True,  # 1:1 relationship for MVP
        index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        ForeignKey("tenants.id"), 
        nullable=False, 
        index=True
    )
    
    # Authentication fields
    email: Mapped[str] = mapped_column(
        String(255), 
        unique=True, 
        nullable=False,
        index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Login tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # MFA fields (for future use)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # User preferences
    language: Mapped[str] = mapped_column(String(10), default="en")
    
    # Relationships
    client: Mapped["Client"] = relationship(
        "Client", 
        back_populates="client_user"
    )
    tenant: Mapped["Tenant"] = relationship("Tenant")

    @property
    def display_name(self) -> str:
        """Get display name from associated client."""
        if self.client:
            return self.client.display_name
        return self.email

