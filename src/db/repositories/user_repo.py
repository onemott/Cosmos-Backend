"""User repository for database operations."""

from typing import Optional, Sequence, List, Dict, Any
from sqlalchemy import select, func, and_
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

    async def get_with_hierarchy(self, user_id: str) -> Optional[User]:
        """Get user with roles, supervisor and subordinates loaded."""
        query = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.roles),
                selectinload(User.supervisor),
                selectinload(User.subordinates),
            )
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

    # ========================================================================
    # Organizational Hierarchy Methods
    # ========================================================================

    async def get_subordinates(
        self, 
        user_id: str, 
        direct_only: bool = True,
        include_roles: bool = False,
    ) -> Sequence[User]:
        """Get subordinates of a user.
        
        Args:
            user_id: The supervisor's user ID
            direct_only: If True, only return direct reports. If False, recursively get all.
            include_roles: If True, eagerly load roles for each user.
        
        Returns:
            List of subordinate users.
        """
        if direct_only:
            query = select(User).where(User.supervisor_id == user_id)
            if include_roles:
                query = query.options(selectinload(User.roles))
            query = query.order_by(User.first_name)
            result = await self.session.execute(query)
            return result.scalars().all()
        else:
            # Recursive query to get all subordinates (using CTE)
            return await self._get_all_subordinates_recursive(user_id, include_roles)

    async def _get_all_subordinates_recursive(
        self, 
        user_id: str,
        include_roles: bool = False,
        max_depth: int = 10,
    ) -> List[User]:
        """Recursively get all subordinates using iteration (to avoid deep recursion).
        
        Args:
            user_id: Starting user ID
            include_roles: Whether to load roles
            max_depth: Maximum depth to traverse (safety limit)
        
        Returns:
            List of all subordinates at all levels.
        """
        all_subordinates: List[User] = []
        current_level_ids = [user_id]
        depth = 0
        
        while current_level_ids and depth < max_depth:
            query = select(User).where(User.supervisor_id.in_(current_level_ids))
            if include_roles:
                query = query.options(selectinload(User.roles))
            result = await self.session.execute(query)
            level_users = list(result.scalars().all())
            
            if not level_users:
                break
                
            all_subordinates.extend(level_users)
            current_level_ids = [str(u.id) for u in level_users]
            depth += 1
        
        return all_subordinates

    async def get_all_subordinate_ids(self, user_id: str, max_depth: int = 10) -> List[str]:
        """Get all subordinate user IDs (recursive).
        
        Useful for filtering queries by team membership.
        
        Args:
            user_id: Starting user ID
            max_depth: Maximum depth to traverse
        
        Returns:
            List of all subordinate user IDs.
        """
        all_ids: List[str] = []
        current_level_ids = [user_id]
        depth = 0
        
        while current_level_ids and depth < max_depth:
            query = select(User.id).where(User.supervisor_id.in_(current_level_ids))
            result = await self.session.execute(query)
            level_ids = [str(row[0]) for row in result.fetchall()]
            
            if not level_ids:
                break
                
            all_ids.extend(level_ids)
            current_level_ids = level_ids
            depth += 1
        
        return all_ids

    async def get_team_scope_user_ids(self, user_id: str, max_depth: int = 10) -> List[str]:
        subordinates = await self.get_all_subordinate_ids(user_id, max_depth=max_depth)
        return [user_id] + subordinates

    async def get_team_tree(self, user_id: str, max_depth: int = 5) -> Dict[str, Any]:
        """Get the complete team tree structure for a user.
        
        Args:
            user_id: The root user ID
            max_depth: Maximum depth to traverse
        
        Returns:
            Dictionary representing the team tree structure.
        """
        user = await self.get_with_roles(user_id)
        if not user:
            return {}
        
        async def build_tree(u: User, current_depth: int) -> Dict[str, Any]:
            node = {
                "id": str(u.id),
                "name": u.full_name,
                "email": u.email,
                "department": u.department,
                "roles": [r.name for r in u.roles] if u.roles else [],
                "subordinates": [],
            }
            
            if current_depth < max_depth:
                direct_subs = await self.get_subordinates(str(u.id), direct_only=True, include_roles=True)
                for sub in direct_subs:
                    sub_tree = await build_tree(sub, current_depth + 1)
                    node["subordinates"].append(sub_tree)
            
            return node
        
        return await build_tree(user, 0)

    async def update_supervisor(
        self, 
        user_id: str, 
        supervisor_id: Optional[str],
    ) -> User:
        """Update a user's supervisor.
        
        Args:
            user_id: The user to update
            supervisor_id: The new supervisor ID (None to remove supervisor)
        
        Returns:
            Updated user.
        
        Raises:
            ValueError: If validation fails.
        """
        user = await self.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        if supervisor_id:
            # Validate supervisor assignment
            is_valid = await self.validate_supervisor_assignment(user_id, supervisor_id)
            if not is_valid:
                raise ValueError("Invalid supervisor assignment")
        
        user.supervisor_id = supervisor_id
        await self.session.flush()
        return user

    async def validate_supervisor_assignment(
        self, 
        user_id: str, 
        supervisor_id: str,
    ) -> bool:
        """Validate that a supervisor assignment is valid.
        
        Checks:
        1. Supervisor exists and is in the same tenant
        2. No circular reference would be created
        3. User is not assigning themselves as supervisor
        
        Args:
            user_id: The user being assigned a supervisor
            supervisor_id: The proposed supervisor
        
        Returns:
            True if valid, False otherwise.
        """
        if user_id == supervisor_id:
            return False  # Can't be your own supervisor
        
        user = await self.get(user_id)
        supervisor = await self.get(supervisor_id)
        
        if not user or not supervisor:
            return False
        
        # Must be in the same tenant
        if user.tenant_id != supervisor.tenant_id:
            return False
        
        # Check for circular reference
        # Walk up the supervisor chain from the proposed supervisor
        current_id = supervisor_id
        visited = {user_id}  # Include user_id to detect cycles
        max_iterations = 20  # Safety limit
        
        for _ in range(max_iterations):
            if current_id in visited:
                return False  # Circular reference detected
            
            visited.add(current_id)
            
            current = await self.get(current_id)
            if not current or not current.supervisor_id:
                break  # Reached top of chain
            
            current_id = current.supervisor_id
        
        return True

    async def get_users_by_supervisor(
        self, 
        supervisor_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[User]:
        """Get all users with a specific supervisor."""
        query = (
            select(User)
            .where(User.supervisor_id == supervisor_id)
            .offset(skip)
            .limit(limit)
            .order_by(User.first_name)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_subordinates(self, user_id: str, direct_only: bool = True) -> int:
        """Count subordinates of a user.
        
        Args:
            user_id: The supervisor's user ID
            direct_only: If True, only count direct reports
        
        Returns:
            Number of subordinates.
        """
        if direct_only:
            query = select(func.count(User.id)).where(User.supervisor_id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        else:
            # Count all subordinates recursively
            all_ids = await self.get_all_subordinate_ids(user_id)
            return len(all_ids)


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

