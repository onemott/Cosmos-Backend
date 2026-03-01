from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from src.api.deps import get_db, get_current_client
from src.services.chat_service import ChatService
from src.services.chat_connection_manager import chat_manager
from src.models.chat import ChatSession
from src.models.client import Client
from sqlalchemy.orm import selectinload

router = APIRouter()

class ChatSessionResponse(BaseModel):
    id: str
    client_id: str
    client_name: str
    advisor_name: Optional[str] = "Support Team"
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

class SendMessageRequest(BaseModel):
    session_id: Optional[str] = None
    content: str
    content_type: str = "text"
    client_side_id: Optional[str] = None

class ChatSessionListResponse(BaseModel):
    sessions: List[ChatSessionResponse]
    total_count: int
    skip: int
    limit: int

    class Config:
        from_attributes = True

@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_my_sessions(
    limit: int = 20,
    offset: int = 0,
    client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions for the current client user."""
    chat_service = ChatService(db)
    sessions, total_count = await chat_service.get_recent_sessions(
        user_id=client["client_user_id"],
        user_type="client_user",
        limit=limit,
        offset=offset
    )
    return {
        "sessions": sessions,
        "total_count": total_count,
        "skip": offset,
        "limit": limit
    }

@router.post("/sessions", response_model=ChatSessionResponse)
async def create_session(
    client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """Create or get an existing chat session."""
    chat_service = ChatService(db)
    session = await chat_service.create_or_get_session(
        client_id=client["client_id"],
        user_id=client["client_user_id"],
        user_type="client_user"
    )
    
    # Enrich session data for response (similar to get_recent_sessions)
    # Since it's a single object, we might need to manually construct the response
    # or rely on the model if it matches. The ChatSessionResponse expects 
    # client_name, last_message_at etc.
    # The session returned by create_or_get_session is a raw DB model.
    # We need to ensure it has the necessary fields populated or return a compatible dict.
    
    # Try to get last message if exists, otherwise None
    last_message = None
    last_message_type = None
    
    # We don't have last_message on the model, so we can default to None for new/retrieved session
    # unless we fetch it. For now, defaulting to None is safer and faster.
    
    # Get Advisor Name (Create session also needs this)
    # We need to reload session to get relationships if not present, or fetch client manually
    # But create_or_get_session already loads client.
    advisor_name = "Support Team"
    if session.client and session.client.assigned_to:
        advisor_name = session.client.assigned_to.full_name

    return {
        "id": str(session.id),
        "client_id": str(session.client_id),
        "client_name": client.get("client_name", "Client"), 
        "advisor_name": advisor_name,
        "last_message_at": session.last_message_at,
        "unread_count": 0,
        "last_message": last_message,
        "last_message_type": last_message_type,
        "status": session.status
    }

@router.get("/sessions/{session_id}/history", response_model=List[ChatMessageResponse])
async def get_my_session_history(
    session_id: str,
    limit: int = 50,
    before: Optional[datetime] = Query(None),
    client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """Get message history."""
    chat_service = ChatService(db)
    
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Security check: Ensure client owns this session
    if session.client_id != client["client_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
        
    messages = await chat_service.get_session_history(session_id, limit=limit, before=before)
    return messages

@router.post("/sessions/{session_id}/read")
async def mark_my_session_read(
    session_id: str,
    client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """Mark all messages in session as read."""
    chat_service = ChatService(db)
    await chat_service.mark_as_read(session_id, client["client_user_id"], "client_user")
    return {"status": "ok"}

@router.post("/messages", response_model=ChatMessageResponse)
async def send_message(
    request: SendMessageRequest,
    client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """Send a message via HTTP (fallback for WebSocket)."""
    chat_service = ChatService(db)
    
    # Determine session_id
    session_id = request.session_id
    if not session_id:
        # Create or get session
        session = await chat_service.create_or_get_session(
            client_id=client["client_id"],
            user_id=client["client_user_id"],
            user_type="client_user"
        )
        session_id = session.id
    else:
        # Verify session belongs to client
        session = await db.get(ChatSession, session_id)
        if not session or session.client_id != client["client_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Save message
    msg = await chat_service.save_message(
        session_id=session_id,
        sender_type="client_user",
        sender_id=client["client_user_id"],
        content=request.content,
        client_side_id=request.client_side_id,
        message_type=request.content_type
    )
    
    # Broadcast to other users via WebSocket
    stmt = select(ChatSession).where(ChatSession.id == session_id).options(
        selectinload(ChatSession.members),
        selectinload(ChatSession.client)
    )
    result = await db.execute(stmt)
    session_with_members = result.scalar_one_or_none()
    
    if session_with_members:
        recipient_ids = []
        for member in session_with_members.members:
            if member.user_type == "user" and member.user_id:
                recipient_ids.append(member.user_id)
        
        if session_with_members.client and session_with_members.client.assigned_to_user_id:
            admin_id = session_with_members.client.assigned_to_user_id
            if admin_id not in recipient_ids:
                recipient_ids.append(admin_id)
        
        if recipient_ids:
            response = {
                "type": "message",
                "id": msg.id,
                "session_id": session_id,
                "sender_id": client["client_user_id"],
                "sender_type": "client_user",
                "content": request.content,
                "content_type": request.content_type,
                "created_at": msg.created_at.isoformat(),
                "client_side_id": request.client_side_id,
                "message_type": request.content_type
            }
            await chat_manager.broadcast(response, recipient_ids)
    
    return msg
