from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from src.api.deps import get_db, require_tenant_user
from src.services.chat_service import ChatService
from src.models.chat import ChatSession

router = APIRouter()

class ChatSessionResponse(BaseModel):
    id: str
    client_id: str
    client_name: str
    last_message_at: datetime
    unread_count: int
    last_message: Optional[str]
    last_message_type: Optional[str]
    status: str

    class Config:
        from_attributes = True

class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    sender_type: str
    sender_id: str
    content: str
    message_type: str
    created_at: datetime
    client_side_id: Optional[str]

    class Config:
        from_attributes = True

class ChatSessionListResponse(BaseModel):
    sessions: List[ChatSessionResponse]
    total_count: int
    skip: int
    limit: int

    class Config:
        from_attributes = True

@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    user: dict = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent chat sessions for the current user."""
    chat_service = ChatService(db)
    sessions, total_count = await chat_service.get_recent_sessions(
        user_id=user["user_id"],
        user_type="user",
        limit=limit,
        offset=offset
    )
    return {
        "sessions": sessions,
        "total_count": total_count,
        "skip": offset,
        "limit": limit
    }

@router.get("/sessions/{session_id}/history", response_model=List[ChatMessageResponse])
async def get_session_history(
    session_id: str,
    limit: int = 50,
    before: Optional[datetime] = Query(None),
    user: dict = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
):
    """Get message history for a session."""
    chat_service = ChatService(db)
    
    # Check existence
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    messages = await chat_service.get_session_history(session_id, limit=limit, before=before)
    return messages

@router.post("/sessions/{session_id}/read")
async def mark_session_read(
    session_id: str,
    user: dict = Depends(require_tenant_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all messages in session as read."""
    chat_service = ChatService(db)
    await chat_service.mark_as_read(session_id, user["user_id"], "user")
    return {"status": "ok"}
