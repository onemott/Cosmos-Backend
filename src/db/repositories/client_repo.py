"""Client repository for database operations."""

from typing import Optional, Sequence, List
from decimal import Decimal
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.repositories.base import BaseRepository
from src.models.client import Client, ClientGroup
from src.models.account import Account


class ClientRepository(BaseRepository[Client]):
    """Repository for Client model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with session."""
        super().__init__(Client, session)

    async def get_by_email(
        self, email: str, tenant_id: str
    ) -> Optional[Client]:
        """Get client by email within a tenant."""
        return await self.get_by_field("email", email, tenant_id=tenant_id)

    async def get_with_accounts(self, client_id: str) -> Optional[Client]:
        """Get client with accounts loaded."""
        query = (
            select(Client)
            .where(Client.id == client_id)
            .options(selectinload(Client.accounts))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_clients_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> Sequence[Client]:
        """Get all clients for a specific tenant."""
        query = (
            select(Client)
            .where(Client.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(Client.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_all_clients(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[Client]:
        """Get all clients across all tenants (super admin only)."""
        query = (
            select(Client)
            .offset(skip)
            .limit(limit)
            .order_by(Client.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_all(self) -> int:
        """Count all clients."""
        query = select(func.count(Client.id))
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count clients in a specific tenant."""
        query = select(func.count(Client.id)).where(
            Client.tenant_id == tenant_id
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def search_clients(
        self,
        search: str,
        tenant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Client]:
        """Search clients by name, email, or entity name."""
        query = select(Client).where(
            (Client.email.ilike(f"%{search}%"))
            | (Client.first_name.ilike(f"%{search}%"))
            | (Client.last_name.ilike(f"%{search}%"))
            | (Client.entity_name.ilike(f"%{search}%"))
        )
        if tenant_id:
            query = query.where(Client.tenant_id == tenant_id)
        query = query.offset(skip).limit(limit).order_by(Client.created_at.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_total_aum(self, tenant_id: Optional[str] = None) -> Decimal:
        """Get total assets under management."""
        query = select(func.coalesce(func.sum(Account.total_value), 0))
        if tenant_id:
            query = query.where(Account.tenant_id == tenant_id)
        result = await self.session.execute(query)
        return Decimal(str(result.scalar() or 0))

    async def get_client_aum(self, client_id: str) -> Decimal:
        """Get total AUM for a specific client."""
        query = select(func.coalesce(func.sum(Account.total_value), 0)).where(
            Account.client_id == client_id
        )
        result = await self.session.execute(query)
        return Decimal(str(result.scalar() or 0))

    # ========================================================================
    # Client Assignment Methods
    # ========================================================================

    async def get_clients_by_assignee(
        self,
        user_id: str,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Client]:
        """Get all clients assigned to a specific user.
        
        Args:
            user_id: The assigned user's ID
            tenant_id: Tenant ID for filtering
            skip: Pagination offset
            limit: Maximum results
        
        Returns:
            List of clients assigned to the user.
        """
        query = (
            select(Client)
            .where(
                Client.tenant_id == tenant_id,
                Client.assigned_to_user_id == user_id,
            )
            .offset(skip)
            .limit(limit)
            .order_by(Client.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_clients_by_team(
        self,
        user_ids: List[str],
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Client]:
        """Get all clients assigned to any user in a list (team).
        
        Args:
            user_ids: List of user IDs (team members)
            tenant_id: Tenant ID for filtering
            skip: Pagination offset
            limit: Maximum results
        
        Returns:
            List of clients assigned to any team member.
        """
        if not user_ids:
            return []
        
        query = (
            select(Client)
            .where(
                Client.tenant_id == tenant_id,
                Client.assigned_to_user_id.in_(user_ids),
            )
            .offset(skip)
            .limit(limit)
            .order_by(Client.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_clients_for_role(
        self,
        user_id: str,
        subordinate_ids: List[str],
        tenant_id: str,
        role_level: str,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> Sequence[Client]:
        """Get clients based on user's role level.
        
        Args:
            user_id: Current user's ID
            subordinate_ids: List of subordinate user IDs (for supervisors)
            tenant_id: Tenant ID
            role_level: One of 'tenant_admin', 'eam_supervisor', 'eam_staff'
            skip: Pagination offset
            limit: Maximum results
            search: Optional search term
            assigned_to: Optional filter by specific assignee
        
        Returns:
            List of clients based on role permissions.
        """
        query = select(Client).where(Client.tenant_id == tenant_id)
        
        # Apply role-based filtering
        if role_level == "eam_staff":
            # Staff can only see their own assigned clients
            query = query.where(Client.assigned_to_user_id == user_id)
        elif role_level == "eam_supervisor":
            # Supervisor can see their own + all subordinates' clients
            all_ids = [user_id] + subordinate_ids
            query = query.where(
                or_(
                    Client.assigned_to_user_id.in_(all_ids),
                    Client.assigned_to_user_id.is_(None),  # Include unassigned
                )
            )
        # tenant_admin sees all (no additional filter)
        
        # Apply optional filters
        if assigned_to:
            query = query.where(Client.assigned_to_user_id == assigned_to)
        
        if search:
            query = query.where(
                or_(
                    Client.email.ilike(f"%{search}%"),
                    Client.first_name.ilike(f"%{search}%"),
                    Client.last_name.ilike(f"%{search}%"),
                    Client.entity_name.ilike(f"%{search}%"),
                )
            )
        
        query = query.offset(skip).limit(limit).order_by(Client.created_at.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_assignee(self, user_id: str, tenant_id: str) -> int:
        """Count clients assigned to a specific user."""
        query = select(func.count(Client.id)).where(
            Client.tenant_id == tenant_id,
            Client.assigned_to_user_id == user_id,
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_by_team(self, user_ids: List[str], tenant_id: str) -> int:
        """Count clients assigned to any user in a team."""
        if not user_ids:
            return 0
        
        query = select(func.count(Client.id)).where(
            Client.tenant_id == tenant_id,
            Client.assigned_to_user_id.in_(user_ids),
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_team_aum(self, user_ids: List[str], tenant_id: str) -> Decimal:
        """Get total AUM for clients assigned to a team.
        
        Args:
            user_ids: List of user IDs (team members)
            tenant_id: Tenant ID
        
        Returns:
            Total AUM as Decimal.
        """
        if not user_ids:
            return Decimal("0")
        
        # Get client IDs for team
        client_query = select(Client.id).where(
            Client.tenant_id == tenant_id,
            Client.assigned_to_user_id.in_(user_ids),
        )
        client_result = await self.session.execute(client_query)
        client_ids = [str(row[0]) for row in client_result.fetchall()]
        
        if not client_ids:
            return Decimal("0")
        
        # Sum AUM for those clients
        aum_query = select(func.coalesce(func.sum(Account.total_value), 0)).where(
            Account.client_id.in_(client_ids)
        )
        result = await self.session.execute(aum_query)
        return Decimal(str(result.scalar() or 0))

    async def reassign_client(
        self,
        client_id: str,
        new_assignee_id: Optional[str],
        tenant_id: str,
    ) -> Optional[Client]:
        """Reassign a client to a different user.
        
        Args:
            client_id: The client to reassign
            new_assignee_id: The new assignee's user ID (None to unassign)
            tenant_id: Tenant ID for verification
        
        Returns:
            Updated client or None if not found.
        """
        client = await self.get(client_id)
        if not client or client.tenant_id != tenant_id:
            return None
        
        client.assigned_to_user_id = new_assignee_id
        await self.session.flush()
        return client

    async def bulk_reassign_clients(
        self,
        client_ids: List[str],
        new_assignee_id: Optional[str],
        tenant_id: str,
    ) -> int:
        """Bulk reassign multiple clients to a user.
        
        Args:
            client_ids: List of client IDs to reassign
            new_assignee_id: The new assignee's user ID
            tenant_id: Tenant ID for verification
        
        Returns:
            Number of clients reassigned.
        """
        count = 0
        for client_id in client_ids:
            client = await self.reassign_client(client_id, new_assignee_id, tenant_id)
            if client:
                count += 1
        return count

    async def get_assignee_breakdown(
        self,
        tenant_id: str,
        user_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        """Get breakdown of clients by assignee.
        
        Args:
            tenant_id: Tenant ID
            user_ids: Optional list of user IDs to filter by
        
        Returns:
            List of dicts with user_id, count, and total_aum.
        """
        query = (
            select(
                Client.assigned_to_user_id,
                func.count(Client.id).label("client_count"),
            )
            .where(Client.tenant_id == tenant_id)
            .group_by(Client.assigned_to_user_id)
        )
        
        if user_ids:
            query = query.where(Client.assigned_to_user_id.in_(user_ids))
        
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        breakdown = []
        for row in rows:
            user_id = str(row[0]) if row[0] else None
            count = row[1]
            
            # Calculate AUM for this user's clients
            if user_id:
                aum = await self.get_team_aum([user_id], tenant_id)
            else:
                aum = Decimal("0")
            
            breakdown.append({
                "user_id": user_id,
                "client_count": count,
                "total_aum": float(aum),
            })
        
        return breakdown


class ClientGroupRepository(BaseRepository[ClientGroup]):
    """Repository for ClientGroup model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with session."""
        super().__init__(ClientGroup, session)

    async def get_groups_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> Sequence[ClientGroup]:
        """Get all client groups for a specific tenant."""
        query = (
            select(ClientGroup)
            .where(ClientGroup.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

