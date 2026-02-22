"""Invitation model for client self-registration."""

import secrets
import string
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, ForeignKey, Enum as SQLEnum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUID


class InvitationStatus(str, Enum):
    """Status of an invitation."""
    PENDING = "pending"
    USED = "used"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


def generate_invitation_code() -> str:
    """Generate a unique, human-readable invitation code.
    
    Format: XXX-XXX-XXX (9 alphanumeric chars, easy to type)
    Example: ABC-DEF-123
    """
    chars = string.ascii_uppercase + string.digits
    # Remove confusing characters (0, O, I, 1, L)
    chars = chars.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')
    
    code_parts = []
    for _ in range(3):
        part = ''.join(secrets.choice(chars) for _ in range(3))
        code_parts.append(part)
    
    return '-'.join(code_parts)


class Invitation(Base, TimestampMixin):
    """
    Invitation for client self-registration.
    
    EAMs create invitations, clients use the code to register themselves.
    """
    
    __tablename__ = "invitations"
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        primary_key=True, 
        default=lambda: str(uuid4())
    )
    
    # Tenant scope
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Who created this invitation
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # The invitation code (unique, human-readable)
    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        default=generate_invitation_code,
        index=True
    )
    
    # Optional: Pre-assign to an existing client record
    client_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Optional: Pre-fill email for the invitee
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Optional: Name hint for the invitee
    invitee_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Optional: Message from EAM to invitee
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Expiration
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    
    # Status
    status: Mapped[InvitationStatus] = mapped_column(
        SQLEnum(InvitationStatus),
        default=InvitationStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # Usage tracking
    used_by_client_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("client_users.id", ondelete="SET NULL"),
        nullable=True
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    tenant = relationship("Tenant", back_populates="invitations")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    client = relationship("Client", foreign_keys=[client_id])
    used_by = relationship("ClientUser", foreign_keys=[used_by_client_user_id])
    
    def __repr__(self) -> str:
        return f"<Invitation(id={self.id}, code={self.code}, status={self.status})>"
    
    @property
    def is_valid(self) -> bool:
        """Check if the invitation is still valid for use."""
        if self.status != InvitationStatus.PENDING:
            return False
        if self.expires_at < datetime.now(timezone.utc):
            return False
        return True
    
    @property
    def is_expired(self) -> bool:
        """Check if the invitation has expired."""
        return self.expires_at < datetime.now(timezone.utc)
    
    def mark_as_used(self, client_user_id: str) -> None:
        """Mark the invitation as used."""
        self.status = InvitationStatus.USED
        self.used_by_client_user_id = client_user_id
        self.used_at = datetime.now(timezone.utc)
    
    def cancel(self) -> None:
        """Cancel the invitation."""
        self.status = InvitationStatus.CANCELLED
    
    @classmethod
    def create_with_defaults(
        cls,
        tenant_id: str,
        created_by_user_id: str,
        expires_in_days: int = 7,
        **kwargs
    ) -> "Invitation":
        """Create an invitation with sensible defaults."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        return cls(
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            **kwargs
        )

