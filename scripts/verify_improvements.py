import httpx
import asyncio
import json

BASE_URL = "http://127.0.0.1:8000"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def print_pass(msg):
    print(f"{GREEN}[PASS] {msg}{RESET}")

def print_fail(msg):
    print(f"{RED}[FAIL] {msg}{RESET}")

async def verify():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, trust_env=False) as client:
        print("Starting verification of App Improvements...")
        
        # 0. Health Check
        print("\n--- 0. Health Check ---")
        try:
            resp = await client.get("/health")
            if resp.status_code == 200:
                print_pass(f"Health check passed: {resp.json()}")
            else:
                print_fail(f"Health check failed: {resp.status_code} {resp.text}")
                return
        except Exception as e:
            print_fail(f"Health check exception: {e}")
            return

        # 1. Login as Admin
        print("\n--- 1. Login as Admin ---")
        try:
            resp = await client.post("/api/v1/auth/login", json={
                "email": "admin@eam-platform.com",
                "password": "admin123"
            })
            if resp.status_code != 200:
                print_fail(f"Admin login failed: {resp.status_code} {resp.text}")
                return
            
            admin_token = resp.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            print_pass("Admin logged in successfully")
        except Exception as e:
            print_fail(f"Admin login exception: {e}")
            return

        # 2. Test System Config (Privacy Policy)
        print("\n--- 2. Test System Config (Privacy Policy) ---")
        
        # 2.1 Get Config (Public) - Before Update
        resp = await client.get("/api/v1/system/config/privacy_policy")
        if resp.status_code == 404:
            print("Privacy policy not set yet (Expected if first run)")
        elif resp.status_code == 200:
            print(f"Current Privacy Policy: {resp.json().get('value')[:50]}...")
        else:
            print_fail(f"Get config failed: {resp.status_code} {resp.text}")

        # 2.2 Update Config (Admin)
        new_policy = "# Privacy Policy\n\nThis is a **Markdown** privacy policy updated by test script."
        resp = await client.put("/api/v1/admin/system/config/privacy_policy", 
                                headers=admin_headers,
                                json={"value": new_policy, "description": "Test Policy", "is_public": True})
        
        if resp.status_code == 200:
            print_pass("Admin updated privacy policy")
        else:
            print_fail(f"Admin update config failed: {resp.status_code} {resp.text}")

        # 2.3 Get Config (Public) - Verify Update
        resp = await client.get("/api/v1/system/config/privacy_policy")
        if resp.status_code == 200 and resp.json().get("value") == new_policy:
            print_pass("Public API verified updated privacy policy")
        else:
            print_fail(f"Public API verify failed: {resp.status_code} {resp.text}")

        # 3. Test Notification System
        print("\n--- 3. Test Notification System ---")

        # 3.1 Send Notification (Admin)
        # We need a user to send to. We will use 'all' or 'tenant' or specific user.
        # Let's try sending to a specific user (Client User) if we can find their ID, 
        # or just send to 'all' for simplicity in test environment.
        # Ideally we should send to the client user we are about to test.
        
        # 3.1 Login as Client User
        print("\n--- 3.1 Login as Client User ---")
        try:
            resp = await client.post("/api/v1/client/auth/login", json={
                "email": "demo@platform-eam.com",
                "password": "Demo1234!"
            })
            if resp.status_code != 200:
                print(f"Client login failed (maybe user doesn't exist?): {resp.status_code}")
                # Try to create it? We assume it exists or run create_demo_client_user.py before this.
                print_fail(f"Client login failed: {resp.status_code} {resp.text}")
                return
            
            client_token = resp.json()["access_token"]
            client_headers = {"Authorization": f"Bearer {client_token}"}
            print_pass("Client logged in successfully")
        except Exception as e:
            print_fail(f"Client login exception: {e}")
            return

        # 3.2 Send Notification (Admin -> All or User)
        # Sending to 'all' to ensure the client gets it.
        notification_payload = {
            "title": "Test Markdown Notification",
            "content": "**Hello** this is a *markdown* notification.",
            "content_format": "markdown",
            "type": "info",
            "target_type": "all" 
        }
        
        resp = await client.post("/api/v1/admin/notifications/send", 
                                 headers=admin_headers, 
                                 json=notification_payload)
        
        if resp.status_code == 200:
            print_pass("Admin sent notification successfully")
        else:
            print_fail(f"Admin send notification failed: {resp.status_code} {resp.text}")

        # 3.3 Verify Notification (Client)
        print("\n--- 3.3 Verify Notification as Client ---")
        resp = await client.get("/api/v1/client/notifications/", headers=client_headers)
        
        if resp.status_code == 200:
            data = resp.json()
            notifications = data.get("items", [])
            # Find our notification
            found = False
            for n in notifications:
                if n.get("title") == "Test Markdown Notification":
                    found = True
                    if n.get("content_format") == "markdown":
                        print_pass("Client received notification with correct format")
                    else:
                        print_fail(f"Client received notification but wrong format: {n.get('content_format')}")
                    break
            
            if not found:
                print_fail("Client did not receive the notification")
                print(f"Received: {len(notifications)} notifications")
        else:
            print_fail(f"Client get notifications failed: {resp.status_code} {resp.text}")

if __name__ == "__main__":
    asyncio.run(verify())
