import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.db.session import async_session_factory
from src.models.user import User
from src.models.client_user import ClientUser
from src.models.client import Client
from src.models.chat import ChatSession, ChatSessionMember

async def check_relations():
    async with async_session_factory() as db:
        print("--- Checking Users ---")
        # Get all admin users
        result = await db.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(f"Admin User: {u.email} (ID: {u.id})")

        print("\n--- Checking Clients ---")
        # Get all clients
        result = await db.execute(select(Client).options(selectinload(Client.assigned_to)))
        clients = result.scalars().all()
        for c in clients:
            assigned_email = c.assigned_to.email if c.assigned_to else "None"
            assigned_id = c.assigned_to.id if c.assigned_to else "None"
            print(f"Client: {c.first_name} {c.last_name} (ID: {c.id})")
            print(f"  -> Assigned To: {assigned_email} (ID: {assigned_id})")
            print(f"  -> Assigned To ID Field: {c.assigned_to_user_id}")

        print("\n--- Checking Client Users ---")
        result = await db.execute(select(ClientUser))
        client_users = result.scalars().all()
        for cu in client_users:
             print(f"Client User: {cu.email} (ID: {cu.id}, ClientID: {cu.client_id})")

        print("\n--- Checking Chat Sessions ---")
        result = await db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.members))
        )
        sessions = result.scalars().all()
        for s in sessions:
            print(f"Session: {s.id} (Client: {s.client_id})")
            for m in s.members:
                print(f"  -> Member: Type={m.user_type}, UserID={m.user_id}, ClientUserID={m.client_user_id}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_relations())
