"""Product and ProductCategory models."""

from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    String,
    Boolean,
    JSON,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant
    from src.models.module import Module


class ProductCategory(Base, TimestampMixin):
    """Product categories - can be platform defaults or tenant-specific.

    Platform defaults have tenant_id=NULL and are available to all tenants.
    Tenant-specific categories have tenant_id set and are only available to that tenant.
    """

    __tablename__ = "product_categories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Category details
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_zh: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Lucide icon name
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="category_rel", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_category_tenant_code"),
    )

    @property
    def is_default(self) -> bool:
        """Check if this is a platform default category."""
        return self.tenant_id is None


class Product(Base, TimestampMixin):
    """Product model representing investment products within modules.

    Platform default products have tenant_id=NULL and is_default=True.
    Tenant-specific products have tenant_id set and is_default=False.
    Tenants can hide platform defaults by setting is_visible=False.
    """

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    module_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identity
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_zh: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    description_zh: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Classification (category string is denormalized for display, category_id is the FK)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)  # conservative/moderate/balanced/growth/aggressive

    # Investment details
    min_investment: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    expected_return: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # True if platform-created

    # Flexible data for additional attributes (tags, features, etc.)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    module: Mapped["Module"] = relationship("Module", back_populates="products")
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    category_rel: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory", back_populates="products"
    )

    __table_args__ = (
        UniqueConstraint("module_id", "tenant_id", "code", name="uq_product_module_tenant_code"),
    )
