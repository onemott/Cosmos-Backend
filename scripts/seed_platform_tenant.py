#!/usr/bin/env python3
"""Seed script to create platform tenant and update system roles.

This script:
1. Creates the Platform Tenant (fixed UUID: 00000000-0000-0000-0000-000000000000)
2. Updates system roles to include new EAM hierarchy roles

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_platform_tenant.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.tenant import Tenant
from src.models.user import Role, User


# Platform tenant configuration (fixed UUID)
PLATFORM_TENANT_ID = "00000000-0000-0000-0000-000000000000"

PLATFORM_TENANT = {
    "id": PLATFORM_TENANT_ID,
    "name": "EAM Platform",
    "slug": "platform",
    "is_active": True,
}

# Updated system roles with new EAM hierarchy
SYSTEM_ROLES = [
    # Platform-level roles (belong to Platform Tenant)
    {
        "name": "super_admin",
        "description": "完整平台访问权限 - 可管理所有租户、模块和平台配置",
        "is_system": True,
    },
    {
        "name": "platform_admin",
        "description": "平台管理员 - 可管理租户和用户，但无超级权限",
        "is_system": True,
    },
    {
        "name": "platform_user",
        "description": "平台只读用户 - 可查看平台统计数据和租户列表",
        "is_system": True,
    },
    # Tenant-level roles (belong to EAM Tenants)
    {
        "name": "tenant_admin",
        "description": "租户管理员 - 完整租户访问权限，可管理用户和客户",
        "is_system": True,
    },
    {
        "name": "eam_supervisor",
        "description": "部门主管 - 可查看和管理下属员工及其负责的客户",
        "is_system": True,
    },
    {
        "name": "eam_staff",
        "description": "普通员工 - 仅可查看和管理自己负责的客户",
        "is_system": True,
    },
]

# Role name mapping for migration (old -> new)
ROLE_MIGRATION_MAP = {
    "tenant_user": "eam_staff",  # Rename tenant_user to eam_staff
}


async def create_platform_tenant():
    """Create or update the platform tenant."""
    async with async_session_factory() as session:
        try:
            # Check if platform tenant exists
            query = select(Tenant).where(Tenant.id == PLATFORM_TENANT_ID)
            result = await session.execute(query)
            existing_tenant = result.scalar_one_or_none()
            
            if existing_tenant:
                print(f"✓  Platform tenant already exists: {existing_tenant.name}")
                # Update properties if needed
                if existing_tenant.name != PLATFORM_TENANT["name"]:
                    existing_tenant.name = PLATFORM_TENANT["name"]
                    print(f"📝 Updated platform tenant name")
                if existing_tenant.slug != PLATFORM_TENANT["slug"]:
                    existing_tenant.slug = PLATFORM_TENANT["slug"]
                    print(f"📝 Updated platform tenant slug")
            else:
                # Create new platform tenant
                tenant = Tenant(**PLATFORM_TENANT)
                session.add(tenant)
                print(f"✅ Created platform tenant: {PLATFORM_TENANT['name']}")
            
            await session.commit()
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating platform tenant: {e}")
            raise


async def seed_roles():
    """Create or update system roles."""
    async with async_session_factory() as session:
        try:
            created_count = 0
            updated_count = 0
            
            # First, handle role migrations (rename old roles)
            for old_name, new_name in ROLE_MIGRATION_MAP.items():
                query = select(Role).where(Role.name == old_name)
                result = await session.execute(query)
                old_role = result.scalar_one_or_none()
                
                if old_role:
                    # Check if new role already exists
                    new_query = select(Role).where(Role.name == new_name)
                    new_result = await session.execute(new_query)
                    new_role = new_result.scalar_one_or_none()
                    
                    if not new_role:
                        # Rename the old role
                        old_role.name = new_name
                        print(f"🔄 Renamed role: {old_name} → {new_name}")
                        updated_count += 1
                    else:
                        print(f"⚠️  Both {old_name} and {new_name} exist, keeping {new_name}")
            
            # Now create/update all system roles
            for role_data in SYSTEM_ROLES:
                query = select(Role).where(Role.name == role_data["name"])
                result = await session.execute(query)
                existing_role = result.scalar_one_or_none()
                
                if existing_role:
                    # Update description if changed
                    if existing_role.description != role_data["description"]:
                        existing_role.description = role_data["description"]
                        existing_role.is_system = role_data["is_system"]
                        updated_count += 1
                        print(f"📝 Updated role: {role_data['name']}")
                    else:
                        print(f"✓  Role exists: {role_data['name']}")
                else:
                    # Create new role
                    role = Role(**role_data)
                    session.add(role)
                    created_count += 1
                    print(f"✅ Created role: {role_data['name']}")
            
            await session.commit()
            
            print(f"\n{'='*60}")
            print(f"🎉 Role Seeding Complete!")
            print(f"{'='*60}")
            print(f"Created: {created_count} roles")
            print(f"Updated: {updated_count} roles")
            print(f"Total: {len(SYSTEM_ROLES)} system roles")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error seeding roles: {e}")
            raise


async def migrate_superusers_to_platform_tenant():
    """Migrate existing superusers to the platform tenant."""
    async with async_session_factory() as session:
        try:
            # Find all users with is_superuser=True
            query = select(User).where(User.is_superuser == True)
            result = await session.execute(query)
            superusers = result.scalars().all()
            
            migrated_count = 0
            for user in superusers:
                if str(user.tenant_id) != PLATFORM_TENANT_ID:
                    old_tenant_id = user.tenant_id
                    user.tenant_id = PLATFORM_TENANT_ID
                    migrated_count += 1
                    print(f"🔄 Migrated superuser {user.email} from tenant {old_tenant_id} to platform tenant")
            
            await session.commit()
            
            if migrated_count > 0:
                print(f"\n✅ Migrated {migrated_count} superuser(s) to platform tenant")
            else:
                print(f"\n✓  No superusers needed migration")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error migrating superusers: {e}")
            raise


async def print_role_matrix():
    """Print the role access matrix for reference."""
    print(f"\n{'='*60}")
    print("📋 Role Access Matrix")
    print(f"{'='*60}")
    print()
    print("Platform Tenant Roles:")
    print("  super_admin    → 完整平台控制权（租户管理、模块管理）")
    print("  platform_admin → 平台管理员（可管理所有租户）")
    print("  platform_user  → 平台只读（查看统计数据）")
    print()
    print("EAM Tenant Roles:")
    print("  tenant_admin   → 租户管理员（完整租户权限，无上级）")
    print("  eam_supervisor → 部门主管（可查看下属数据）")
    print("  eam_staff      → 普通员工（仅看自己负责的数据）")
    print()
    print(f"{'='*60}")
    print("📊 Data Access Rules")
    print(f"{'='*60}")
    print()
    print("客户数据访问:")
    print("  tenant_admin   → 查看租户内所有客户")
    print("  eam_supervisor → 查看自己 + 递归下属负责的客户")
    print("  eam_staff      → 仅查看 assigned_to_user_id = 自己的客户")
    print()
    print(f"{'='*60}\n")


async def main():
    """Main function to run all seeding operations."""
    print("🚀 Starting Platform Tenant and Role Setup...\n")
    
    # Step 1: Create platform tenant
    print("Step 1: Creating Platform Tenant...")
    await create_platform_tenant()
    print()
    
    # Step 2: Seed roles
    print("Step 2: Seeding System Roles...")
    await seed_roles()
    print()
    
    # Step 3: Migrate superusers (optional, uncomment if needed)
    # print("Step 3: Migrating Superusers to Platform Tenant...")
    # await migrate_superusers_to_platform_tenant()
    # print()
    
    # Print role matrix for reference
    await print_role_matrix()
    
    print("✅ Platform setup complete!")


if __name__ == "__main__":
    asyncio.run(main())
