import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.user import User
from src.models.notification import Notification

ADMIN_EMAIL = "admin@eam-platform.com"

async def seed_notifications():
    async with async_session_factory() as session:
        # Find all active users
        print("Fetching all active users...")
        query = select(User).where(User.is_active == True)
        result = await session.execute(query)
        users = result.scalars().all()
        
        if not users:
            print("No active users found!")
            return

        print(f"Found {len(users)} users. Generating notifications for all...")
        
        total_notifications = 0
        
        for user in users:
            print(f"  -> Generating for {user.email}...")
            notifications = []

            # 1. Markdown Notifications (3)
            for i in range(3):
                content = f"""
# Weekly Report {i+1}

Here is your weekly summary:

| Metric | Value |
| :--- | :--- |
| Users | {100 + i} |
| Revenue | ${1000 + i*10} |

**Key Highlights:**
* Growth is *steady*
* New features deployed
                """
                notifications.append(Notification(
                    user_id=user.id,
                    title=f"Markdown Report {i+1}",
                    content=content,
                    content_format="markdown",
                    type="system"
                ))

            # 2. Deep Link Notifications (2)
            for i in range(2):
                notifications.append(Notification(
                    user_id=user.id,
                    title=f"New Client Assigned {i+1}",
                    content=f"You have been assigned a new client. Click to view.",
                    content_format="text",
                    type="alert",
                    metadata_json={"link": "/clients"}
                ))

            # 3. Plain Text Notifications (15 for pagination test)
            for i in range(15):
                notifications.append(Notification(
                    user_id=user.id,
                    title=f"System Update {i+1}",
                    content=f"System maintenance scheduled for next Sunday. (Item {i+1})",
                    content_format="text",
                    type="system"
                ))

            session.add_all(notifications)
            total_notifications += len(notifications)

        await session.commit()
        print(f"Successfully created {total_notifications} notifications for {len(users)} users.")

if __name__ == "__main__":
    asyncio.run(seed_notifications())
