import asyncio
import sys
import os
from uuid import uuid4

# Add current directory to path so imports work
sys.path.append(os.getcwd())

from src.db.session import async_session_factory
from src.models.user import User
from src.models.tenant import Tenant
from src.models.client import Client
from src.models.client_user import ClientUser
from src.core.security import pwd_context
from sqlalchemy import select

async def create_client_user():
    try:
        async with async_session_factory() as session:
            # 1. Get Tenant
            print("Checking tenant...")
            stmt = select(Tenant).limit(1)
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()
            
            if not tenant:
                print("No tenant found. Please run create_demo_user.py first (or creating one now).")
                tenant = Tenant(
                    id=str(uuid4()),
                    name="Demo Tenant",
                    slug="demo-tenant",
                    domain="demo.platform-eam.com"
                )
                session.add(tenant)
                await session.commit()
                await session.refresh(tenant)
                print(f"Created tenant: {tenant.id}")
            else:
                print(f"Using existing tenant: {tenant.id}")

            # 2. Check/Create Client
            print("Checking Client...")
            # Check if there is a client for this tenant
            stmt = select(Client).where(Client.tenant_id == tenant.id).limit(1)
            result = await session.execute(stmt)
            client = result.scalar_one_or_none()

            if not client:
                print("Client not found. Creating Client...")
                client = Client(
                    id=str(uuid4()),
                    tenant_id=tenant.id,
                    first_name="Demo",
                    last_name="Client",
                    email="demo@platform-eam.com",
                    client_type="individual",
                    kyc_status="approved"
                )
                session.add(client)
                await session.commit()
                await session.refresh(client)
                print(f"Created Client: {client.id}")
            else:
                print(f"Using existing Client: {client.id}")

            # 3. Check/Create ClientUser
            print("Checking ClientUser...")
            stmt = select(ClientUser).where(ClientUser.email == 'demo@platform-eam.com')
            result = await session.execute(stmt)
            client_user = result.scalar_one_or_none()

            if not client_user:
                print("ClientUser not found. Creating ClientUser...")
                hashed_pw = pwd_context.hash("Demo1234!")
                client_user = ClientUser(
                    id=str(uuid4()),
                    client_id=client.id,
                    tenant_id=tenant.id,
                    email='demo@platform-eam.com',
                    hashed_password=hashed_pw,
                    is_active=True,
                    language="en"
                )
                session.add(client_user)
                await session.commit()
                print("Created ClientUser: demo@platform-eam.com")
            else:
                print("ClientUser already exists.")
                # Update password to be sure
                client_user.hashed_password = pwd_context.hash("Demo1234!")
                await session.commit()
                print("Updated ClientUser password.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(create_client_user())
