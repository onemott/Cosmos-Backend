import sys
import os
import asyncio
import httpx
from sqlalchemy import select, delete
from src.db.session import async_session_factory
from src.models.client_user import ClientUser
from src.models.notification import Notification
from create_demo_client_user import create_client_user

# Setup paths
sys.path.append(os.getcwd())

async def main():
    try:
        # 1. Ensure Demo User Exists
        print("Creating/Checking demo user...")
        await create_client_user()
        
        client_user_id = None
        # 2. Get ClientUser ID
        async with async_session_factory() as session:
            stmt = select(ClientUser).where(ClientUser.email == 'demo@platform-eam.com')
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                print("Error: ClientUser not found after creation attempt.")
                return
            client_user_id = user.id
            
            # Clean up old notifications
            await session.execute(delete(Notification).where(Notification.client_user_id == client_user_id))
            
            # 3. Create Test Notifications directly in DB
            print("Creating test notifications...")
            notes = [
                Notification(
                    client_user_id=client_user_id,
                    title="Test Notification 1",
                    content="Content 1",
                    type="system",
                    is_read=False
                ),
                Notification(
                    client_user_id=client_user_id,
                    title="Test Notification 2",
                    content="Content 2",
                    type="alert",
                    is_read=True
                ),
                Notification(
                    client_user_id=client_user_id,
                    title="Test Notification 3",
                    content="Content 3",
                    type="promotion",
                    is_read=False
                )
            ]
            session.add_all(notes)
            await session.commit()
            print("Created 3 notifications (2 unread, 1 read)")

        # 4. Test API
        base_url = "http://127.0.0.1:8000/api/v1"
        
        async with httpx.AsyncClient(trust_env=False) as client:
            # Login
            print("Logging in...")
            resp = await client.post(f"{base_url}/client/auth/login", json={
                "email": "demo@platform-eam.com",
                "password": "Demo1234!"
            })
            if resp.status_code != 200:
                print(f"Login failed: {resp.status_code} {resp.text}")
                return
                
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Get List
            print("Testing GET /client/notifications/...")
            resp = await client.get(f"{base_url}/client/notifications/", headers=headers)
            if resp.status_code != 200:
                print(f"GET list failed: {resp.status_code} {resp.text}")
                return
                
            data = resp.json()
            print(f"List response: Total {data['total']}, Unread {data['unread_count']}")
            
            if data["total"] != 3:
                print(f"FAILURE: Expected 3 items, got {data['total']}")
            if data["unread_count"] != 2:
                print(f"FAILURE: Expected 2 unread, got {data['unread_count']}")
            
            if len(data["items"]) > 0:
                note_id = data["items"][0]["id"]
                
                # Mark Read
                print(f"Testing PATCH /client/notifications/{note_id}/read...")
                resp = await client.patch(f"{base_url}/client/notifications/{note_id}/read", headers=headers)
                if resp.status_code == 200:
                    print("Mark Read OK")
                else:
                    print(f"Mark Read Failed: {resp.status_code}")

            # Get Unread Count
            print("Testing GET /client/notifications/unread-count...")
            resp = await client.get(f"{base_url}/client/notifications/unread-count", headers=headers)
            print(f"Unread Count: {resp.json()}")
            
            # Mark All Read
            print("Testing POST /client/notifications/read-all...")
            resp = await client.post(f"{base_url}/client/notifications/read-all", headers=headers)
            if resp.status_code == 200:
                print(f"Mark All Read OK: {resp.json()}")
            else:
                print(f"Mark All Read Failed: {resp.status_code}")
            
            # Verify Count is 0
            resp = await client.get(f"{base_url}/client/notifications/unread-count", headers=headers)
            final_count = resp.json()
            if final_count == 0:
                print("Final Unread Count is 0 OK")
            else:
                print(f"FAILURE: Final Unread Count is {final_count}, expected 0")
                
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
