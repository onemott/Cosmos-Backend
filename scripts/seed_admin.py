#!/usr/bin/env python3
"""Seed script to create an admin user for development.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_admin.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.user import User
from src.models.tenant import Tenant
from src.core.security import hash_password


# Default admin credentials - CHANGE IN PRODUCTION!
ADMIN_EMAIL = "admin@eam-platform.com"
ADMIN_PASSWORD = "admin123"
ADMIN_FIRST_NAME = "Admin"
ADMIN_LAST_NAME = "User"

# Dev tenant ID (must match the one we created earlier)
DEV_TENANT_ID = "00000000-0000-0000-0000-000000000000"


async def seed_admin():
    """Create the development admin user."""
    async with async_session_factory() as session:
        try:
            # Check if dev tenant exists
            tenant = await session.get(Tenant, DEV_TENANT_ID)
            if not tenant:
                print(f"❌ Dev tenant not found. Creating it first...")
                tenant = Tenant(
                    id=DEV_TENANT_ID,
                    name="Development Tenant",
                    slug="dev",
                    is_active=True,
                )
                session.add(tenant)
                await session.flush()
                print(f"✅ Created dev tenant: {tenant.name}")
            
            # Check if admin user already exists
            query = select(User).where(User.email == ADMIN_EMAIL)
            result = await session.execute(query)
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                print(f"⚠️  Admin user already exists: {ADMIN_EMAIL}")
                print(f"   Updating password...")
                existing_user.hashed_password = hash_password(ADMIN_PASSWORD)
                await session.commit()
                print(f"✅ Password updated!")
                return
            
            # Create admin user
            admin_user = User(
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASSWORD),
                first_name=ADMIN_FIRST_NAME,
                last_name=ADMIN_LAST_NAME,
                tenant_id=DEV_TENANT_ID,
                is_active=True,
                is_superuser=True,
            )
            session.add(admin_user)
            await session.commit()
            
            print(f"✅ Admin user created successfully!")
            print(f"")
            print(f"   Email:    {ADMIN_EMAIL}")
            print(f"   Password: {ADMIN_PASSWORD}")
            print(f"")
            print(f"⚠️  IMPORTANT: Change these credentials in production!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating admin user: {e}")
            raise


if __name__ == "__main__":
    print("🔐 Seeding admin user...")
    print("")
    asyncio.run(seed_admin())

