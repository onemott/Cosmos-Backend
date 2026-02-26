"""Client notification API endpoints."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_client
from src.db.repositories.notification_repo import NotificationRepository
from src.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
)

router = APIRouter(prefix="/client/notifications", tags=["Client Notifications"])

@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
) -> Any:
    """Get current client user's notifications."""
    repo = NotificationRepository(db)
    client_user_id = current_client["client_user_id"]
    items, total = await repo.get_by_user(
        client_user_id=client_user_id, skip=skip, limit=limit
    )
    unread_count = await repo.get_unread_count(client_user_id=client_user_id)
    
    return NotificationListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        skip=skip,
        limit=limit,
    )

@router.get("/unread-count", response_model=int)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
) -> Any:
    """Get unread notification count."""
    repo = NotificationRepository(db)
    return await repo.get_unread_count(client_user_id=current_client["client_user_id"])

@router.patch("/{id}/read", response_model=NotificationResponse)
async def mark_read(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
) -> Any:
    """Mark a notification as read."""
    repo = NotificationRepository(db)
    notification = await repo.get(id)
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    if str(notification.client_user_id) != str(current_client["client_user_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    updated = await repo.update(notification, {"is_read": True})
    return updated

@router.post("/read-all", response_model=dict)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
) -> Any:
    """Mark all notifications as read."""
    repo = NotificationRepository(db)
    count = await repo.mark_all_read(client_user_id=current_client["client_user_id"])
    return {"count": count}

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
) -> None:
    """Delete a notification."""
    repo = NotificationRepository(db)
    notification = await repo.get(id)
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    if str(notification.client_user_id) != str(current_client["client_user_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    await repo.delete(notification)
