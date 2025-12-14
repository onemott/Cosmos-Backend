"""Client and ClientGroup models."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import String, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant
    from src.models.account import Account, BankConnection
    from src.models.document import Document
    from src.models.task import Task
    from src.models.module import ClientModule
    from src.models.client_user import ClientUser


class ClientType(str, enum.Enum):
    """Client type enumeration."""

    INDIVIDUAL = "individual"
    ENTITY = "entity"
    TRUST = "trust"


class RiskProfile(str, enum.Enum):
    """Risk profile enumeration."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    BALANCED = "balanced"
    GROWTH = "growth"
    AGGRESSIVE = "aggressive"


class KYCStatus(str, enum.Enum):
    """KYC status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ClientGroup(Base, TimestampMixin):
    """Client group / household model."""

    __tablename__ = "client_groups"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Relationships
    clients: Mapped[list["Client"]] = relationship("Client", back_populates="group")


class Client(Base, TimestampMixin):
    """Client model (individual or entity)."""

    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True
    )
    group_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("client_groups.id"), nullable=True
    )

    # Basic information
    client_type: Mapped[ClientType] = mapped_column(
        SQLEnum(ClientType), default=ClientType.INDIVIDUAL
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # KYC and compliance
    kyc_status: Mapped[KYCStatus] = mapped_column(
        SQLEnum(KYCStatus), default=KYCStatus.PENDING
    )
    risk_profile: Mapped[Optional[RiskProfile]] = mapped_column(
        SQLEnum(RiskProfile), nullable=True
    )

    # Additional data
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="clients")
    group: Mapped[Optional["ClientGroup"]] = relationship(
        "ClientGroup", back_populates="clients"
    )
    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="client")
    bank_connections: Mapped[list["BankConnection"]] = relationship(
        "BankConnection", back_populates="client"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="client"
    )
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="client")
    modules: Mapped[list["ClientModule"]] = relationship(
        "ClientModule", back_populates="client", cascade="all, delete-orphan"
    )
    client_user: Mapped[Optional["ClientUser"]] = relationship(
        "ClientUser", back_populates="client", uselist=False
    )

    @property
    def display_name(self) -> str:
        """Get display name based on client type."""
        if self.client_type == ClientType.INDIVIDUAL:
            return f"{self.first_name} {self.last_name}"
        return self.entity_name or "Unknown"

