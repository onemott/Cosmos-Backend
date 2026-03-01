from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from src.api.deps import get_db, get_current_ws_user
from src.services.chat_connection_manager import chat_manager
from src.services.chat_service import ChatService
from src.models.chat import ChatSession
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user: dict = Depends(get_current_ws_user),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time chat.
    Supports:
    - sending messages (type="message")
    - read receipts (type="read")
    - heartbeats (type="ping")
    """
    logger.info(f"WebSocket connection attempt from user: {user}")
    user_id = user["user_id"]
    user_type = user["user_type"] # "client" or "user"
    
    # Map auth user_type to db user_type
    db_user_type = "client_user" if user_type == "client" else "user"
    
    # Accept connection
    await chat_manager.connect(websocket, user_id)
    
    chat_service = ChatService(db)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            # Handle heartbeat
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
                
            # Handle message
            if msg_type == "message":
                logger.info(f"Received message: {data}")
                logger.info(f"User info - user_id: {user_id}, user_type: {user_type}, db_user_type: {db_user_type}, client_id: {user.get('client_id')}")
                # Support both formats: {type: "message", data: {...}} and {type: "message", ...}
                message_data = data.get("data", data)  # Get nested data or use entire object
                content = message_data.get("content")
                client_side_id = message_data.get("client_side_id")
                message_type = message_data.get("message_type", "text")
                session_id = message_data.get("session_id")
                
                # Determine session_id
                if user_type == "client":
                    # For client, if session_id not provided, get/create one
                    client_id = user.get("client_id")
                    if not client_id:
                        logger.error(f"Client user {user_id} has no client_id")
                        continue
                        
                    session = await chat_service.create_or_get_session(client_id, user_id, "client_user")
                    session_id = session.id
                else:
                    # For admin/staff, session_id is required
                    if not session_id:
                         await websocket.send_json({"type": "error", "message": "session_id required for staff"})
                         continue
                
                # Save message
                msg = await chat_service.save_message(
                    session_id=session_id,
                    sender_type=db_user_type,
                    sender_id=user_id,
                    content=content,
                    client_side_id=client_side_id,
                    message_type=message_type
                )
                
                # Broadcast to all members
                # Fetch members using select instead of get (get doesn't support options)
                stmt = select(ChatSession).where(ChatSession.id == session_id).options(
                    selectinload(ChatSession.members),
                    selectinload(ChatSession.client)
                )
                result = await chat_service.db.execute(stmt)
                session_with_members = result.scalar_one_or_none()
                
                if session_with_members:
                    recipient_ids = []
                    debug_info = []

                    # Add session members
                    for member in session_with_members.members:
                        if member.user_type == "user" and member.user_id:
                            recipient_ids.append(member.user_id)
                            debug_info.append(f"Member(User):{member.user_id}")
                        elif member.user_type == "client_user" and member.client_user_id:
                            recipient_ids.append(member.client_user_id)
                            debug_info.append(f"Member(Client):{member.client_user_id}")
                    
                    # Ensure assigned admin also gets the message even if not joined yet
                    if session_with_members.client and session_with_members.client.assigned_to_user_id:
                        admin_id = session_with_members.client.assigned_to_user_id
                        logger.info(f"Client assigned_to_user_id: {admin_id}")
                        if admin_id not in recipient_ids:
                            recipient_ids.append(admin_id)
                            debug_info.append(f"Assigned:{admin_id}")
                    
                    logger.info(f"Broadcasting message {msg.id} to: {debug_info}")
                    logger.info(f"Current active WS connections: {list(chat_manager.active_connections.keys())}")

                    # Prepare payload - flat structure for compatibility
                    response = {
                        "type": "message",
                        "id": msg.id,
                        "session_id": session_id,
                        "sender_id": user_id,
                        "sender_type": db_user_type,
                        "content": content,
                        "content_type": message_type,
                        "created_at": msg.created_at.isoformat(),
                        "client_side_id": client_side_id,
                        "message_type": message_type
                    }
                    
                    await chat_manager.broadcast(response, recipient_ids)
                    
                    # Send ACK to sender (only to the sending device)
                    await websocket.send_json({
                        "type": "ack",
                        "client_side_id": client_side_id,
                        "status": "ok",
                        "message_id": msg.id
                    })
            
            # Handle read receipt
            elif msg_type == "read":
                 session_id = data.get("session_id")
                 if session_id:
                     await chat_service.mark_as_read(
                         session_id=session_id, 
                         user_id=user_id, 
                         user_type=db_user_type
                     )

    except WebSocketDisconnect:
        chat_manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        # Try to close if not already closed
        try:
            await websocket.close()
        except:
            pass
        chat_manager.disconnect(websocket, user_id)
