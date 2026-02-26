from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import get_current_user, get_db, is_platform_admin, is_tenant_admin
from src.models.notification import Notification
from src.models.client_user import ClientUser
from src.schemas.notification import NotificationSendRequest, NotificationListResponse, NotificationResponse
from src.db.repositories.notification_repo import NotificationRepository

router = APIRouter()

@router.get("/notifications/mine", response_model=NotificationListResponse)
async def get_my_notifications(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get current admin user's notifications.
    """
    repo = NotificationRepository(db)
    user_id = current_user.get("user_id")
    
    items, total = await repo.get_by_user(user_id=user_id, skip=skip, limit=limit)
    unread_count = await repo.get_unread_count(user_id=user_id)
    
    return {
        "items": items,
        "total": total,
        "unread_count": unread_count,
        "skip": skip,
        "limit": limit
    }

@router.patch("/notifications/{id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark a notification as read.
    """
    repo = NotificationRepository(db)
    user_id = current_user.get("user_id")
    
    notification = await repo.get(id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
        
    if notification.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this notification"
        )
        
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    
    return notification

@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark all notifications as read for the current user.
    """
    repo = NotificationRepository(db)
    user_id = current_user.get("user_id")
    
    count = await repo.mark_all_read(user_id=user_id)
    await db.commit()
    
    return {"message": "All notifications marked as read", "count": count}

async def create_notifications_batch(
    db: AsyncSession,
    user_ids: List[str],
    title: str,
    content: str,
    content_format: str,
    type: str,
    metadata_json: Optional[dict] = None
):
    """Helper to create notifications for multiple client users."""
    notifications = [
        Notification(
            client_user_id=uid,
            title=title,
            content=content,
            content_format=content_format,
            type=type,
            metadata_json=metadata_json
        )
        for uid in user_ids
    ]
    db.add_all(notifications)
    await db.commit()

@router.post("/notifications/send")
async def send_notification(
    request: NotificationSendRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Send notifications to client users.
    
    Target types:
    - user: Send to specific client user (requires tenant admin of that user's tenant)
    - tenant: Send to all client users in a tenant (requires tenant admin of that tenant)
    - all: Send to all client users in the platform (requires platform admin)
    """
    
    target_user_ids = []
    
    if request.target_type == "all":
        if not is_platform_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can send system-wide notifications"
            )
        
        # Get all client users
        result = await db.execute(select(ClientUser.id).where(ClientUser.is_active == True))
        target_user_ids = result.scalars().all()
        
    elif request.target_type == "tenant":
        tenant_id = request.target_id
        if not tenant_id:
            # If not specified, use current user's tenant
            tenant_id = current_user.get("tenant_id")
            
        if not tenant_id:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant ID is required"
            )
            
        # Check permission
        if not is_platform_admin(current_user):
            if current_user.get("tenant_id") != tenant_id or not is_tenant_admin(current_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to send notifications to this tenant"
                )
        
        # Get tenant client users
        result = await db.execute(
            select(ClientUser.id).where(
                ClientUser.tenant_id == tenant_id,
                ClientUser.is_active == True
            )
        )
        target_user_ids = result.scalars().all()
        
    elif request.target_type == "user":
        user_id = request.target_id
        if not user_id:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target user ID is required"
            )
            
        # Verify user exists and check permission
        result = await db.execute(select(ClientUser).where(ClientUser.id == user_id))
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        if not is_platform_admin(current_user):
            if current_user.get("tenant_id") != str(target_user.tenant_id) or not is_tenant_admin(current_user):
                 raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to send notifications to this user"
                )
        
        target_user_ids = [user_id]
    
    if not target_user_ids:
        return {"message": "No users found to send notification", "count": 0}
        
    # Create notifications in background to avoid blocking
    # Note: For very large batches, this should be a Celery task.
    # For now, FastAPI background task is sufficient for moderate loads.
    # However, since we need db session, passing db to background task is tricky 
    # because session might be closed. 
    # We will do it synchronously for now as it's an admin action and safer for data integrity
    # unless we create a new session in background.
    
    # Let's do it in the request for reliability in this MVP phase
    await create_notifications_batch(
        db, 
        target_user_ids, 
        request.title, 
        request.content, 
        request.content_format,
        request.type, 
        request.metadata_json
    )
    
    return {
        "message": "Notifications queued successfully",
        "count": len(target_user_ids)
    }
