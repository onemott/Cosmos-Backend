import requests
import json

BASE_URL = "http://localhost:8000/api/v1"
EMAIL = "admin@eam-platform.com"
PASSWORD = "admin123"

def test_notifications():
    # 1. Login
    print(f"Logging in as {EMAIL}...")
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            return
        
        token = resp.json()["access_token"]
        print("Login successful. Token obtained.")
        
        # 2. Get Notifications
        print("Fetching notifications...")
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BASE_URL}/admin/notifications/mine", headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"Success! Found {data['total']} notifications.")
            print(f"Unread count: {data['unread_count']}")
            print(f"DEBUG USER ID: {data.get('debug_user_id')}")
            if data['items']:
                print(f"First item: {data['items'][0]['title']}")
            else:
                print("No items found.")
        else:
            print(f"Failed to get notifications: {resp.status_code} {resp.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_notifications()
