import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add current directory to path so imports work
sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient
from sqlalchemy import text
from src.main import app
from src.db.session import async_session_factory, engine
from src.core.config import settings

# Remove global client
# client = TestClient(app) 

def test_database_connection():
    """Test if the database connection can be established."""
    print("Testing Database Connection...", end=" ", flush=True)
    async def check_db():
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        # Dispose engine to avoid loop conflicts with TestClient later
        await engine.dispose()
    
    # Use asyncio.run
    try:
        asyncio.run(check_db())
        print("✓ OK")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        # raise e # Don't raise here to allow other tests to run? No, DB is critical.
        raise e

def test_app_startup_and_docs():
    """Test if the application starts and serves documentation."""
    print("Testing App Startup & Docs...", end=" ", flush=True)
    with TestClient(app) as client:
        # Check OpenAPI JSON
        response = client.get("/api/openapi.json")
        
        if settings.debug:
            if response.status_code != 200:
                print(f"❌ FAILED: Status {response.status_code}")
                raise Exception(f"OpenAPI endpoint failed: {response.status_code}")
            
            data = response.json()
            if "openapi" not in data:
                print("❌ FAILED: Invalid OpenAPI response")
                raise Exception("Invalid OpenAPI response")
    
    print("✓ OK")

def test_authentication_flow():
    """Test the full authentication flow: Login -> Get User -> Get Tenants."""
    print("Testing Authentication Flow...", end=" ", flush=True)
    
    with TestClient(app) as client:
        # A. Login
        login_payload = {
            "email": "admin@eam-platform.com",
            "password": "admin123" 
        }
        
        response = client.post("/api/v1/auth/login", json=login_payload)
        if response.status_code != 200:
            print(f"❌ FAILED: Login failed with {response.status_code} - {response.text}")
            raise Exception(f"Login failed: {response.text}")
        
        tokens = response.json()
        if "access_token" not in tokens:
            print("❌ FAILED: No access_token in response")
            raise Exception("No access_token returned")
        
        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # B. Get Current User (/users/me)
        response = client.get("/api/v1/users/me", headers=headers)
        if response.status_code != 200:
            print(f"❌ FAILED: Get User failed with {response.status_code} - {response.text}")
            raise Exception(f"Get User failed: {response.text}")
        
        user_data = response.json()
        # print(f"DEBUG: User Roles: {user_data.get('roles')}")
        if user_data["email"] != login_payload["email"]:
            print(f"❌ FAILED: Email mismatch (expected {login_payload['email']}, got {user_data.get('email')})")
            raise Exception("Email mismatch")
        
        # C. List Tenants
        response = client.get("/api/v1/tenants/", headers=headers)
        if response.status_code != 200:
            print(f"❌ FAILED: List Tenants failed with {response.status_code} - {response.text}")
            raise Exception(f"List Tenants failed: {response.text}")
        
        tenants = response.json()
        if not isinstance(tenants, list):
            print("❌ FAILED: Tenants response is not a list")
            raise Exception("Tenants response is not a list")
        
        print(f"✓ OK (Found {len(tenants)} tenants)")

if __name__ == "__main__":
    print("="*40)
    print("STARTING SMOKE TEST")
    print("="*40)
    
    try:
        test_database_connection()
        test_app_startup_and_docs()
        test_authentication_flow()
        
        print("\n" + "="*40)
        print("✅ ALL SMOKE TESTS PASSED")
        print("="*40)
        sys.exit(0)
    except Exception as e:
        print("\n" + "="*40)
        print("❌ SMOKE TEST FAILED")
        print("="*40)
        sys.exit(1)
