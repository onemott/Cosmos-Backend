"""Notification repository."""

from typing import Sequence, Optional
from sqlalchemy import select, func, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.base import BaseRepository
from src.models.notification import Notification

class NotificationRepository(BaseRepository[Notification]):
    """Notification repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Notification, session)

    async def get_by_user(
        self, user_id: str = None, client_user_id: str = None, skip: int = 0, limit: int = 100
    ) -> tuple[Sequence[Notification], int]:
        """Get notifications for a user (staff or client)."""
        query = select(Notification)
        
        if user_id:
            query = query.where(Notification.user_id == user_id)
        elif client_user_id:
            query = query.where(Notification.client_user_id == client_user_id)
        else:
            return [], 0
            
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        
        # Get items
        query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        items = result.scalars().all()
        
        return items, total

    async def get_unread_count(self, user_id: str = None, client_user_id: str = None) -> int:
        """Get unread notification count for a user."""
        query = select(func.count()).select_from(Notification).where(Notification.is_read == False)
        
        if user_id:
            query = query.where(Notification.user_id == user_id)
        elif client_user_id:
            query = query.where(Notification.client_user_id == client_user_id)
        else:
            return 0
            
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def mark_all_read(self, user_id: str = None, client_user_id: str = None) -> int:
        """Mark all notifications as read for a user."""
        stmt = update(Notification).where(Notification.is_read == False).values(is_read=True)
        
        if user_id:
            stmt = stmt.where(Notification.user_id == user_id)
        elif client_user_id:
            stmt = stmt.where(Notification.client_user_id == client_user_id)
        else:
            return 0
            
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
