#!/usr/bin/env python3
"""
Seed script for creating test accounts for all role levels.

This script creates test users for each role in the hierarchy:
- Platform Tenant roles: super_admin, platform_admin, platform_user
- EAM Tenant roles: tenant_admin, eam_supervisor, eam_staff

Usage:
    cd backend
    python scripts/seed_role_accounts.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.user import User, Role
from src.models.tenant import Tenant
from src.core.security import hash_password


# Platform tenant configuration
PLATFORM_TENANT_ID = "00000000-0000-0000-0000-000000000000"

# Test users configuration for each role
TEST_USERS = {
    # Platform Tenant Roles
    "super_admin": {
        "email": "superadmin@platform.com",
        "password": "SuperAdmin123!",
        "first_name": "Super",
        "last_name": "Administrator",
        "is_superuser": True,
        "department": "Platform Operations",
        "employee_code": "PLT001"
    },
    "platform_admin": {
        "email": "platformadmin@platform.com",
        "password": "PlatformAdmin123!",
        "first_name": "Platform",
        "last_name": "Administrator",
        "is_superuser": False,
        "department": "Platform Management",
        "employee_code": "PLT002"
    },
    "platform_user": {
        "email": "platformuser@platform.com",
        "password": "PlatformUser123!",
        "first_name": "Platform",
        "last_name": "User",
        "is_superuser": False,
        "department": "Platform Analytics",
        "employee_code": "PLT003"
    },
    # EAM Tenant Roles - Tenant Admin (no supervisor)
    "tenant_admin": {
        "email": "tenantadmin@testfirm.com",
        "password": "TenantAdmin123!",
        "first_name": "Tenant",
        "last_name": "Administrator",
        "is_superuser": False,
        "department": "Executive Management",
        "employee_code": "TFM001",
        "supervisor_email": None  # No supervisor
    },
    # EAM Tenant Roles - Supervisor (reports to tenant admin)
    "eam_supervisor": {
        "email": "supervisor@testfirm.com",
        "password": "Supervisor123!",
        "first_name": "Department",
        "last_name": "Supervisor",
        "is_superuser": False,
        "department": "Investment Advisory",
        "employee_code": "TFM002",
        "supervisor_email": "tenantadmin@testfirm.com"
    },
    # EAM Tenant Roles - Staff (reports to supervisor)
    "eam_staff": {
        "email": "staff@testfirm.com",
        "password": "Staff123!",
        "first_name": "Regular",
        "last_name": "Staff",
        "is_superuser": False,
        "department": "Client Services",
        "employee_code": "TFM003",
        "supervisor_email": "supervisor@testfirm.com"
    }
}


async def get_platform_tenant(session):
    """Get the platform tenant."""
    query = select(Tenant).where(Tenant.id == PLATFORM_TENANT_ID)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_test_tenant(session):
    """Get or create a test EAM tenant."""
    # Try to find existing test tenant
    query = select(Tenant).where(Tenant.slug.like('%test%'))
    result = await session.execute(query)
    tenants = result.scalars().all()
    
    if tenants:
        # Use the first test tenant found
        tenant = tenants[0]
        print(f"✅ Using existing test tenant: {tenant.name}")
    else:
        # Create test tenant
        tenant = Tenant(
            id=str(uuid4()),
            name="Test EAM Firm",
            slug="test-firm-role-demo",
            contact_email="contact@test-firm.com",
            is_active=True,
            settings={"description": "Test tenant for role hierarchy demonstration"}
        )
        session.add(tenant)
        await session.flush()
        print(f"✅ Created test tenant: {tenant.name}")
    
    return tenant


async def get_role_by_name(session, role_name):
    """Get role by name."""
    query = select(Role).where(Role.name == role_name)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def assign_role_to_user(session, user, role):
    """Assign role to user."""
    from sqlalchemy import text
    
    # Check if assignment already exists
    check_query = text(
        "SELECT 1 FROM user_roles WHERE user_id = :user_id AND role_id = :role_id"
    )
    check_result = await session.execute(
        check_query, 
        {"user_id": str(user.id), "role_id": str(role.id)}
    )
    existing = check_result.scalar_one_or_none()
    
    if not existing:
        # Insert role assignment
        insert_query = text(
            "INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"
        )
        await session.execute(
            insert_query,
            {"user_id": str(user.id), "role_id": str(role.id)}
        )
        print(f"  ✅ Assigned role '{role.name}' to {user.email}")


async def create_user_with_role(session, role_name, user_data, tenant):
    """Create user and assign role."""
    # Check if user already exists
    query = select(User).where(User.email == user_data["email"])
    result = await session.execute(query)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        print(f"  ⚠️  User {user_data['email']} already exists, updating...")
        existing_user.hashed_password = hash_password(user_data["password"])
        existing_user.first_name = user_data["first_name"]
        existing_user.last_name = user_data["last_name"]
        existing_user.is_active = True
        user = existing_user
    else:
        print(f"  👤 Creating user: {user_data['first_name']} {user_data['last_name']}")
        
        # Handle supervisor assignment
        supervisor_id = None
        if user_data.get("supervisor_email"):
            sup_query = select(User).where(User.email == user_data["supervisor_email"])
            sup_result = await session.execute(sup_query)
            supervisor = sup_result.scalar_one_or_none()
            if supervisor:
                supervisor_id = supervisor.id
                print(f"    Reports to: {supervisor.first_name} {supervisor.last_name}")
            else:
                print(f"    ⚠️  Supervisor {user_data['supervisor_email']} not found")
        
        user = User(
            id=str(uuid4()),
            email=user_data["email"],
            hashed_password=hash_password(user_data["password"]),
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            tenant_id=tenant.id,
            is_active=True,
            is_superuser=user_data.get("is_superuser", False),
            supervisor_id=supervisor_id,
            department=user_data.get("department"),
            employee_code=user_data.get("employee_code")
        )
        session.add(user)
        await session.flush()
    
    # Assign role
    role = await get_role_by_name(session, role_name)
    if role:
        await assign_role_to_user(session, user, role)
    else:
        print(f"  ❌ Role '{role_name}' not found!")
    
    return user


async def seed_role_accounts():
    """Main seed function."""
    print("=" * 60)
    print("Creating Test Accounts for All Role Levels")
    print("=" * 60)
    
    async with async_session_factory() as session:
        try:
            # Get tenants
            platform_tenant = await get_platform_tenant(session)
            if not platform_tenant:
                print("❌ Platform tenant not found!")
                return
            
            test_tenant = await get_test_tenant(session)
            
            print(f"\n🏢 Platform Tenant: {platform_tenant.name}")
            print(f"🏢 Test EAM Tenant: {test_tenant.name}")
            
            created_users = []
            
            # Create users for each role
            for role_name, user_data in TEST_USERS.items():
                print(f"\n📋 Creating account for role: {role_name}")
                
                # Determine which tenant to use
                if role_name in ["super_admin", "platform_admin", "platform_user"]:
                    tenant = platform_tenant
                    print(f"  Using platform tenant")
                else:
                    tenant = test_tenant
                    print(f"  Using test EAM tenant")
                
                user = await create_user_with_role(session, role_name, user_data, tenant)
                if user:
                    created_users.append({
                        "role": role_name,
                        "email": user_data["email"],
                        "password": user_data["password"],
                        "tenant": tenant.name,
                        "name": f"{user_data['first_name']} {user_data['last_name']}"
                    })
            
            await session.commit()
            
            # Print summary
            print("\n" + "=" * 60)
            print("✅ Role Account Creation Complete!")
            print("=" * 60)
            
            if created_users:
                print("\n📋 Test Credentials by Role:")
                print("-" * 40)
                
                # Group by tenant
                platform_users = [u for u in created_users if "Platform" in u["tenant"]]
                eam_users = [u for u in created_users if "Test EAM" in u["tenant"]]
                
                if platform_users:
                    print("\n🌐 Platform Tenant Accounts:")
                    for user in platform_users:
                        print(f"  Role: {user['role']}")
                        print(f"  Name: {user['name']}")
                        print(f"  Email: {user['email']}")
                        print(f"  Password: {user['password']}")
                        print()
                
                if eam_users:
                    print("🏢 EAM Tenant Accounts:")
                    for user in eam_users:
                        print(f"  Role: {user['role']}")
                        print(f"  Name: {user['name']}")
                        print(f"  Email: {user['email']}")
                        print(f"  Password: {user['password']}")
                        print()
                
                print("📊 Role Hierarchy Structure:")
                print("  super_admin")
                print("    └── platform_admin")
                print("        └── platform_user")
                print("  tenant_admin (Test EAM Firm)")
                print("    └── eam_supervisor")
                print("        └── eam_staff")
                
                print(f"\n⚠️  IMPORTANT: These are test accounts - change passwords before production!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error: {e}")
            raise


if __name__ == "__main__":
    print("🚀 Starting Role Account Seeding...")
    print("")
    asyncio.run(seed_role_accounts())