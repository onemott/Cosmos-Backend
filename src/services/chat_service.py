from typing import Optional, List, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.models.chat import ChatSession, ChatSessionMember, ChatMessage
from src.models.client import Client
from src.models.client_user import ClientUser
from src.models.user import User
from src.core.logging import get_logger

logger = get_logger(__name__)

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_get_session(self, client_id: str, user_id: str, user_type: str) -> ChatSession:
        """
        Get active session for client or create new one.
        If creating, automatically add assigned user as member.
        Ensures the current user is a member.
        """
        # 1. Try to find existing active session
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.client_id == client_id, ChatSession.status == "active")
            .options(
                selectinload(ChatSession.members),
                selectinload(ChatSession.client).selectinload(Client.assigned_to)
            )
        )
        session = result.scalar_one_or_none()
        
        if session:
            # Ensure current user is a member
            await self._ensure_member(session.id, user_id, user_type)
            
            # If current user is client_user, also ensure assigned user is a member
            # This handles cases where session exists but assigned user changed or wasn't added
            if user_type == "client_user":
                client_result = await self.db.execute(select(Client).where(Client.id == client_id))
                client = client_result.scalar_one_or_none()
                if client and client.assigned_to_user_id:
                    await self._ensure_member(session.id, client.assigned_to_user_id, "user")
            
            return session

        # 2. Create new session
        session = ChatSession(client_id=client_id, status="active")
        self.db.add(session)
        await self.db.flush() # Get ID
        
        # 3. Add members
        # Add current user
        await self._ensure_member(session.id, user_id, user_type)

        # If current user is client_user, add Assigned User (Advisor)
        if user_type == "client_user":
            client_result = await self.db.execute(select(Client).where(Client.id == client_id))
            client = client_result.scalar_one_or_none()
            
            if client and client.assigned_to_user_id:
                 await self._ensure_member(session.id, client.assigned_to_user_id, "user")
        
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def _ensure_member(self, session_id: str, user_id: str, user_type: str):
        """Add user to session if not already a member."""
        # Check if exists
        query = select(ChatSessionMember).where(
            ChatSessionMember.session_id == session_id,
            ChatSessionMember.user_type == user_type
        )
        if user_type == "user":
            query = query.where(ChatSessionMember.user_id == user_id)
        else:
            query = query.where(ChatSessionMember.client_user_id == user_id)
            
        result = await self.db.execute(query)
        member = result.scalar_one_or_none()
        
        if not member:
            member = ChatSessionMember(
                session_id=session_id,
                user_type=user_type,
                last_read_at=datetime.now(timezone.utc)
            )
            if user_type == "user":
                member.user_id = user_id
            else:
                member.client_user_id = user_id
            self.db.add(member)
            await self.db.flush()  # Flush to ensure member is added before commit

    async def save_message(
        self, 
        session_id: str, 
        sender_type: str, 
        sender_id: str, 
        content: str, 
        client_side_id: Optional[str] = None, 
        message_type: str = "text"
    ) -> ChatMessage:
        """Save message and update session timestamp."""
        # Deduplication
        if client_side_id:
            existing = await self.db.execute(
                select(ChatMessage).where(ChatMessage.client_side_id == client_side_id)
            )
            msg = existing.scalar_one_or_none()
            if msg:
                return msg

        message = ChatMessage(
            session_id=session_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            client_side_id=client_side_id,
            message_type=message_type
        )
        self.db.add(message)
        
        # Update session last_message_at
        session = await self.db.get(ChatSession, session_id)
        if session:
            session.last_message_at = func.now()
            self.db.add(session)
            
        try:
            await self.db.commit()
            await self.db.refresh(message)
            return message
        except IntegrityError:
            await self.db.rollback()
            # Retry check for duplicate (race condition)
            if client_side_id:
                existing = await self.db.execute(
                    select(ChatMessage).where(ChatMessage.client_side_id == client_side_id)
                )
                msg = existing.scalar_one_or_none()
                if msg:
                    return msg
            raise

    async def mark_as_read(self, session_id: str, user_id: str, user_type: str):
        """Update last_read_at for a member."""
        query = select(ChatSessionMember).where(
            ChatSessionMember.session_id == session_id,
            ChatSessionMember.user_type == user_type
        )
        if user_type == "user":
            query = query.where(ChatSessionMember.user_id == user_id)
        else:
            query = query.where(ChatSessionMember.client_user_id == user_id)
            
        result = await self.db.execute(query)
        member = result.scalar_one_or_none()
        
        if member:
            member.last_read_at = datetime.now(timezone.utc)
            self.db.add(member)
            await self.db.commit()
        else:
            # Auto-join if not member? For now just ignore or log warning
            logger.warning(f"User {user_id} ({user_type}) tried to mark read but is not member of session {session_id}")

    async def get_recent_sessions(self, user_id: str, user_type: str, limit: int = 20, offset: int = 0) -> tuple[List[dict], int]:
        """
        Get sessions for a user, ordered by last_message_at desc.
        Includes unread count.
        Returns (sessions, total_count).
        """
        logger.info(f"Getting sessions for {user_type} {user_id}")
        
        count_stmt = None
        list_stmt = None
        
        if user_type == "client_user":
            # For client users, show all sessions for their client, even if they haven't joined yet
            # First get the client_id
            client_user_res = await self.db.execute(select(ClientUser).where(ClientUser.id == user_id))
            client_user = client_user_res.scalar_one_or_none()
            
            if not client_user:
                logger.warning(f"Client user {user_id} not found")
                return [], 0
                
            # Subquery for member info (read time)
            member_alias = select(ChatSessionMember).where(
                ChatSessionMember.user_type == user_type,
                ChatSessionMember.client_user_id == user_id
            ).subquery()

            # Base conditions
            base_conditions = [ChatSession.client_id == client_user.client_id]

            # Count query
            count_stmt = select(func.count(ChatSession.id)).where(*base_conditions)

            # List query
            list_stmt = (
                select(ChatSession, member_alias.c.last_read_at)
                .outerjoin(member_alias, ChatSession.id == member_alias.c.session_id)
                .where(*base_conditions)
                .options(
                    selectinload(ChatSession.client).selectinload(Client.assigned_to)
                )
                .order_by(desc(ChatSession.last_message_at))
                .offset(offset)
                .limit(limit)
            )
        else:
            # For staff, show sessions they are members of OR assigned to via Client
            member_alias = select(ChatSessionMember).where(
                ChatSessionMember.user_type == user_type,
                ChatSessionMember.user_id == user_id
            ).subquery()
            
            # Complex condition for staff visibility
            visibility_condition = or_(
                member_alias.c.session_id.is_not(None),
                Client.assigned_to_user_id == user_id
            )
            
            # Count query
            # Note: For count we need joins similar to list query to ensure correct filtering
            count_stmt = (
                select(func.count(ChatSession.id))
                .outerjoin(member_alias, ChatSession.id == member_alias.c.session_id)
                .join(ChatSession.client)
                .where(visibility_condition)
            )

            # List query
            list_stmt = (
                select(ChatSession, member_alias.c.last_read_at)
                .outerjoin(member_alias, ChatSession.id == member_alias.c.session_id)
                .join(ChatSession.client)
                .where(visibility_condition)
                .options(
                    selectinload(ChatSession.client).selectinload(Client.assigned_to)
                )
                .order_by(desc(ChatSession.last_message_at))
                .offset(offset)
                .limit(limit)
            )
        
        # Execute Count
        total_count_res = await self.db.execute(count_stmt)
        total_count = total_count_res.scalar() or 0

        # Execute List
        result = await self.db.execute(list_stmt)
        sessions_with_read_time = result.all()
        
        logger.info(f"Found {len(sessions_with_read_time)} sessions for {user_id} (Total: {total_count})")
        
        output = []
        for session, last_read_at in sessions_with_read_time:
            # Count unread
            # Optimization: could be done in main query but complex with SQLAlchemy
            unread_count = 0
            if last_read_at:
                count_res = await self.db.execute(
                    select(func.count(ChatMessage.id))
                    .where(
                        ChatMessage.session_id == session.id,
                        ChatMessage.created_at > last_read_at
                    )
                )
                unread_count = count_res.scalar()
            else:
                # If never read, count all? Or count all since join?
                # Assume all if last_read_at is None
                count_res = await self.db.execute(
                    select(func.count(ChatMessage.id))
                    .where(ChatMessage.session_id == session.id)
                )
                unread_count = count_res.scalar()
                
            # Get last message content
            last_msg_res = await self.db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session.id)
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            last_msg = last_msg_res.scalar_one_or_none()
            
            # Get Advisor Name
            advisor_name = "Support Team"
            if session.client and session.client.assigned_to:
                advisor_name = session.client.assigned_to.full_name

            output.append({
                "id": session.id,
                "client_id": session.client_id,
                "client_name": session.client.display_name if session.client else "Unknown",
                "advisor_name": advisor_name,
                "last_message_at": session.last_message_at,
                "unread_count": unread_count,
                "last_message": last_msg.content if last_msg else None,
                "last_message_type": last_msg.message_type if last_msg else None,
                "status": session.status
            })
            
        return output, total_count

    async def get_session_history(self, session_id: str, limit: int = 50, before: Optional[datetime] = None) -> List[ChatMessage]:
        """Get message history."""
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(limit)
        )
        
        if before:
            query = query.where(ChatMessage.created_at < before)
            
        result = await self.db.execute(query)
        return result.scalars().all()
