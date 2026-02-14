import asyncio
import sys
import os
from uuid import uuid4

# Add current directory to path so imports work
sys.path.append(os.getcwd())

from src.db.session import async_session_factory
from src.models.user import User
from src.models.tenant import Tenant
from src.core.security import pwd_context
from sqlalchemy import select

async def create_data():
    try:
        async with async_session_factory() as session:
            # 1. Check/Create Tenant
            print("Checking tenant...")
            stmt = select(Tenant).limit(1)
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()
            
            if not tenant:
                print("No tenant found. Creating one...")
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

            # 2. Check/Create User
            print("Checking user...")
            stmt = select(User).where(User.email == 'demo@platform-eam.com')
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                print("User not found. Creating user...")
                hashed_pw = pwd_context.hash("Demo1234!")
                user = User(
                    id=str(uuid4()),
                    email='demo@platform-eam.com',
                    hashed_password=hashed_pw,
                    first_name='Demo',
                    last_name='User',
                    is_active=True,
                    is_superuser=False,
                    tenant_id=tenant.id
                )
                session.add(user)
                await session.commit()
                print("Created user: demo@platform-eam.com")
            else:
                print("User already exists.")
                # Optional: Update password just in case
                user.hashed_password = pwd_context.hash("Demo1234!")
                await session.commit()
                print("Updated user password.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(create_data())
