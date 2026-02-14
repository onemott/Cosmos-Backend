"""User repository for database operations."""

from typing import Optional, Sequence
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.repositories.base import BaseRepository
from src.models.user import User, Role


class UserRepository(BaseRepository[User]):
    """Repository for User model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with session."""
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        return await self.get_by_field("email", email)

    async def get_by_email_for_auth(self, email: str) -> Optional[User]:
        """Get user by email with roles loaded for authentication."""
        query = (
            select(User)
            .where(User.email == email)
            .options(selectinload(User.roles))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[User]:
        """Get user by external authentication provider ID."""
        return await self.get_by_field("external_id", external_id)

    async def get_with_roles(self, user_id: str) -> Optional[User]:
        """Get user with roles loaded."""
        query = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_users_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> Sequence[User]:
        """Get all users for a specific tenant."""
        query = (
            select(User)
            .where(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_all_users(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[User]:
        """Get all users across all tenants (super admin only)."""
        query = (
            select(User)
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_all(self) -> int:
        """Count all users."""
        query = select(func.count(User.id))
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count users in a specific tenant."""
        query = select(func.count(User.id)).where(User.tenant_id == tenant_id)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_active(self) -> int:
        """Count active users."""
        query = select(func.count(User.id)).where(User.is_active == True)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def search_users(
        self,
        search: str,
        tenant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[User]:
        """Search users by name or email."""
        query = select(User).where(
            (User.email.ilike(f"%{search}%"))
            | (User.first_name.ilike(f"%{search}%"))
            | (User.last_name.ilike(f"%{search}%"))
        )
        if tenant_id:
            query = query.where(User.tenant_id == tenant_id)
        query = query.offset(skip).limit(limit).order_by(User.first_name)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def assign_roles(self, user_id: str, role_ids: list[str]) -> User:
        """Assign roles to a user (replaces existing roles)."""
        user = await self.get_with_roles(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Get role objects
        query = select(Role).where(Role.id.in_(role_ids))
        result = await self.session.execute(query)
        roles = result.scalars().all()
        
        # Replace user's roles
        user.roles = list(roles)
        await self.session.commit()  # Commit to persist the many-to-many changes
        
        # Re-fetch with roles eagerly loaded (refresh doesn't load relationships)
        return await self.get_with_roles(user_id)

    async def add_role(self, user_id: str, role_id: str) -> User:
        """Add a single role to user."""
        user = await self.get_with_roles(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        role = await self.session.get(Role, role_id)
        if not role:
            raise ValueError(f"Role {role_id} not found")
        
        if role not in user.roles:
            user.roles.append(role)
            await self.session.flush()
        
        return user

    async def remove_role(self, user_id: str, role_id: str) -> User:
        """Remove a single role from user."""
        user = await self.get_with_roles(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        role = await self.session.get(Role, role_id)
        if role and role in user.roles:
            user.roles.remove(role)
            await self.session.flush()
        
        return user

    async def get_by_email_for_auth(self, email: str) -> Optional[User]:
        """Get user by email with roles loaded (for authentication)."""
        query = (
            select(User)
            .where(User.email == email)
            .options(selectinload(User.roles))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class RoleRepository(BaseRepository[Role]):
    """Repository for Role model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with session."""
        super().__init__(Role, session)

    async def get_by_name(self, name: str) -> Optional[Role]:
        """Get role by name."""
        return await self.get_by_field("name", name)

    async def get_system_roles(self) -> Sequence[Role]:
        """Get all system roles."""
        query = select(Role).where(Role.is_system == True)
        result = await self.session.execute(query)
        return result.scalars().all()

