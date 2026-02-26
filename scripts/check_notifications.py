import asyncio
import sys
from pathlib import Path
from sqlalchemy import select, func
from src.db.session import async_session_factory
from src.models.user import User
from src.models.notification import Notification

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def check_data():
    async with async_session_factory() as session:
        # 1. Check Users
        print("--- Checking Users ---")
        query = select(User)
        result = await session.execute(query)
        users = result.scalars().all()
        print(f"Total Users: {len(users)}")
        for u in users:
            print(f"User: {u.email} (ID: {u.id}, Active: {u.is_active})")
            
            # Check notifications for this user
            n_query = select(func.count()).select_from(Notification).where(Notification.user_id == u.id)
            n_result = await session.execute(n_query)
            count = n_result.scalar()
            print(f"  -> Notifications count: {count}")
            
            if count > 0:
                # Show latest notification
                latest_query = select(Notification).where(Notification.user_id == u.id).order_by(Notification.created_at.desc()).limit(1)
                latest_result = await session.execute(latest_query)
                latest = latest_result.scalar_one()
                print(f"  -> Latest: {latest.title} (Read: {latest.is_read}, Created: {latest.created_at})")

        # 2. Check Total Notifications
        print("\n--- Checking Total Notifications ---")
        total_query = select(func.count()).select_from(Notification)
        total_result = await session.execute(total_query)
        print(f"Total Notifications in DB: {total_result.scalar()}")

if __name__ == "__main__":
    asyncio.run(check_data())
