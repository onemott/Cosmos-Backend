"""User and RBAC models."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import String, Boolean, ForeignKey, Table, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant


# Association table for User-Role many-to-many
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=False), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=False), ForeignKey("roles.id"), primary_key=True),
)

# Association table for Role-Permission many-to-many
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=False), ForeignKey("roles.id"), primary_key=True),
    Column(
        "permission_id",
        UUID(as_uuid=False),
        ForeignKey("permissions.id"),
        primary_key=True,
    ),
)


class User(Base, TimestampMixin):
    """User model."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # External auth provider ID (Auth0/Cognito)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Organizational hierarchy fields
    supervisor_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary=user_roles, back_populates="users"
    )
    
    # Self-referential relationship for organizational hierarchy
    supervisor: Mapped[Optional["User"]] = relationship(
        "User",
        remote_side=[id],
        back_populates="subordinates",
        foreign_keys=[supervisor_id],
    )
    subordinates: Mapped[list["User"]] = relationship(
        "User",
        back_populates="supervisor",
        foreign_keys="[User.supervisor_id]",
    )

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        return f"{self.first_name} {self.last_name}"


class Role(Base, TimestampMixin):
    """Role model for RBAC."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )


class Permission(Base):
    """Permission model for fine-grained access control."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # read, write, delete, etc.
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )


# Alias for backwards compatibility
UserRole = user_roles

