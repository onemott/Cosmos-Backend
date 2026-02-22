"""Module and feature flag models."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
import enum

from sqlalchemy import String, Boolean, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.tenant import Tenant
    from src.models.client import Client
    from src.models.product import Product


class ModuleCategory(str, enum.Enum):
    """Module category enumeration."""

    BASIC = "basic"
    INVESTMENT = "investment"
    ANALYTICS = "analytics"


class Module(Base, TimestampMixin):
    """Allocation product / feature module model."""

    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Module details
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_zh: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    description_zh: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    category: Mapped[ModuleCategory] = mapped_column(
        SQLEnum(ModuleCategory), default=ModuleCategory.BASIC
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)

    # Configuration schema
    config_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tenant_modules: Mapped[list["TenantModule"]] = relationship(
        "TenantModule", back_populates="module", cascade="all, delete-orphan"
    )
    client_modules: Mapped[list["ClientModule"]] = relationship(
        "ClientModule", back_populates="module", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="module", cascade="all, delete-orphan"
    )


class TenantModule(Base, TimestampMixin):
    """Tenant-module association with configuration."""

    __tablename__ = "tenant_modules"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False
    )

    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Configuration
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="modules")
    module: Mapped["Module"] = relationship("Module", back_populates="tenant_modules")


class ClientModule(Base, TimestampMixin):
    """Client-module association with configuration (Phase 2)."""

    __tablename__ = "client_modules"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False
    )

    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Configuration
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    client: Mapped["Client"] = relationship("Client", back_populates="modules")
    module: Mapped["Module"] = relationship("Module", back_populates="client_modules")

