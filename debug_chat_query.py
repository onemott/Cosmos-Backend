import asyncio
import sys
import os
from sqlalchemy import select, desc, or_
from sqlalchemy.orm import selectinload

# Add project root to path
sys.path.append(os.getcwd())

from src.db.session import async_session_factory
from src.models.user import User
from src.models.client_user import ClientUser
from src.models.client import Client
from src.models.chat import ChatSession, ChatSessionMember

async def debug_query():
    # IDs from previous debug output
    supervisor_id = "4f85c37e-6d97-439c-b525-30d885bc5371"
    client_user_id = "4bc824a5-44e5-411a-a36e-aadfae108836"
    
    print(f"Checking for Supervisor: {supervisor_id}")
    print(f"Checking for Client User: {client_user_id}")
    
    async with async_session_factory() as db:
        # 1. Simulate Client User Query
        print("\n=== Simulating Client User Query ===")
        user_id = client_user_id
        user_type = "client_user"
        
        client_user_res = await db.execute(select(ClientUser).where(ClientUser.id == user_id))
        client_user = client_user_res.scalar_one_or_none()
        
        if client_user:
            print(f"Client User found. Client ID: {client_user.client_id}")
            
            member_alias = select(ChatSessionMember).where(
                ChatSessionMember.user_type == user_type,
                ChatSessionMember.client_user_id == user_id
            ).subquery()

            stmt = (
                select(ChatSession, member_alias.c.last_read_at)
                .outerjoin(member_alias, ChatSession.id == member_alias.c.session_id)
                .where(ChatSession.client_id == client_user.client_id)
                .options(
                    selectinload(ChatSession.client).selectinload(Client.assigned_to)
                )
                .order_by(desc(ChatSession.last_message_at))
            )
            
            result = await db.execute(stmt)
            sessions = result.all()
            print(f"Found {len(sessions)} sessions for Client User.")
            for s, read_at in sessions:
                print(f" - Session {s.id}, Last Msg At: {s.last_message_at}, Status: {s.status}")
        else:
            print("Client User not found!")

        # 2. Simulate Supervisor Query
        print("\n=== Simulating Supervisor (Staff) Query ===")
        user_id = supervisor_id
        user_type = "user"
        
        member_alias = select(ChatSessionMember).where(
            ChatSessionMember.user_type == user_type,
            ChatSessionMember.user_id == user_id
        ).subquery()
        
        stmt = (
            select(ChatSession, member_alias.c.last_read_at)
            .outerjoin(member_alias, ChatSession.id == member_alias.c.session_id)
            .join(ChatSession.client)
            .where(
                or_(
                    member_alias.c.session_id.is_not(None),
                    Client.assigned_to_user_id == user_id
                )
            )
            .options(
                selectinload(ChatSession.client).selectinload(Client.assigned_to)
            )
            .order_by(desc(ChatSession.last_message_at))
        )
        
        result = await db.execute(stmt)
        sessions = result.all()
        print(f"Found {len(sessions)} sessions for Supervisor.")
        for s, read_at in sessions:
            assigned_id = s.client.assigned_to_user_id if s.client else "None"
            print(f" - Session {s.id}, Client Assigned To: {assigned_id}, Last Msg At: {s.last_message_at}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(debug_query())
