#!/usr/bin/env python3
"""
Seed script for creating test client accounts for different tenants.

This script creates test clients with different module access patterns
to demonstrate the multi-tenant product visibility system.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_test_clients.py

    # With reset (clears existing test data first):
    python scripts/seed_test_clients.py --reset
"""

import asyncio
import argparse
import sys
import os
from uuid import uuid4

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory
from src.core.security import hash_password
from src.models.tenant import Tenant
from src.models.client import Client, ClientType, KYCStatus, RiskProfile
from src.models.client_user import ClientUser
from src.models.module import Module, TenantModule, ClientModule


# ============================================================================
# 测试客户定义
# ============================================================================

# 按租户 slug 组织的待创建测试客户配置
# 请根据数据库中的实际租户 slug 更新下方键名！
TEST_CLIENTS = {
    # 平台租户——拥有全部模块访问权限的示例客户
    "platform": [
        {
            "email": "demo@platform-eam.com",
            "password": "Demo1234!",
            "first_name": "Demo",
            "last_name": "User",
            "risk_profile": RiskProfile.BALANCED,
            # 未设置模块限制——自动获得租户启用的所有模块
            "disabled_modules": [],
        },
    ],
    # 测试 EAM Firm 租户——展示不同访问级别的客户
    "test-firm": [
        {
            "email": "alice@testeam-firm.com",
            "password": "Test1234!",
            "first_name": "Alice",
            "last_name": "Investor",
            "risk_profile": RiskProfile.GROWTH,
            # Alice 拥有租户全部模块的访问权限
            "disabled_modules": [],
        },
        {
            "email": "bob@testeam-firm.com",
            "password": "Test1234!",
            "first_name": "Bob",
            "last_name": "Conservative",
            "risk_profile": RiskProfile.CONSERVATIVE,
            # Bob 的访问受限——禁用替代投资和 AI 推荐模块
            "disabled_modules": ["alternative_investments", "ai_recommendations"],
        },
    ],
}


# ============================================================================
# Seed Functions
# ============================================================================

async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    """Get tenant by slug."""
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def get_all_tenants(db: AsyncSession) -> list[Tenant]:
    """Get all tenants."""
    result = await db.execute(select(Tenant).where(Tenant.is_active == True))
    return list(result.scalars().all())


async def get_tenant_enabled_modules(db: AsyncSession, tenant_id: str) -> list[Module]:
    """Get modules enabled for a tenant (core + explicitly enabled)."""
    # Get all active modules
    result = await db.execute(select(Module).where(Module.is_active == True))
    all_modules = result.scalars().all()

    # Get tenant module status
    tm_result = await db.execute(
        select(TenantModule).where(TenantModule.tenant_id == tenant_id)
    )
    tenant_modules = {tm.module_id: tm for tm in tm_result.scalars().all()}

    enabled = []
    for module in all_modules:
        if module.is_core:
            enabled.append(module)
        elif module.id in tenant_modules and tenant_modules[module.id].is_enabled:
            enabled.append(module)

    return enabled


async def create_client_with_modules(
    db: AsyncSession,
    tenant: Tenant,
    client_data: dict,
) -> Client | None:
    """Create a client with specific module access."""

    # Check if client already exists
    result = await db.execute(
        select(ClientUser).where(ClientUser.email == client_data["email"])
    )
    existing = result.scalar_one_or_none()

    if existing:
        print(f"    Client {client_data['email']} already exists, skipping...")
        return None

    print(f"    Creating client: {client_data['first_name']} {client_data['last_name']}")

    # Create Client
    client = Client(
        id=str(uuid4()),
        tenant_id=tenant.id,
        client_type=ClientType.INDIVIDUAL,
        first_name=client_data["first_name"],
        last_name=client_data["last_name"],
        email=client_data["email"],
        kyc_status=KYCStatus.APPROVED,
        risk_profile=client_data.get("risk_profile", RiskProfile.BALANCED),
    )
    db.add(client)
    await db.flush()

    # Create ClientUser (login credentials)
    client_user = ClientUser(
        id=str(uuid4()),
        client_id=client.id,
        tenant_id=tenant.id,
        email=client_data["email"],
        hashed_password=hash_password(client_data["password"]),
        is_active=True,
    )
    db.add(client_user)

    # Get tenant enabled modules
    enabled_modules = await get_tenant_enabled_modules(db, tenant.id)
    disabled_codes = set(client_data.get("disabled_modules", []))

    # Create ClientModule records for disabled modules
    for module in enabled_modules:
        if module.code in disabled_codes:
            # Explicitly disable this module for the client
            client_module = ClientModule(
                id=str(uuid4()),
                tenant_id=tenant.id,
                client_id=client.id,
                module_id=module.id,
                is_enabled=False,
            )
            db.add(client_module)
            print(f"      Disabled module: {module.code}")

    await db.commit()

    print(f"      Login: {client_data['email']} / {client_data['password']}")

    return client


async def reset_test_clients(db: AsyncSession):
    """Delete test clients."""
    print("\nResetting test clients...")

    all_emails = []
    for clients in TEST_CLIENTS.values():
        all_emails.extend([c["email"] for c in clients])

    result = await db.execute(
        select(ClientUser).where(ClientUser.email.in_(all_emails))
    )
    test_users = result.scalars().all()

    for user in test_users:
        # Delete client modules
        await db.execute(
            delete(ClientModule).where(ClientModule.client_id == user.client_id)
        )

        # Delete client user
        await db.execute(
            delete(ClientUser).where(ClientUser.id == user.id)
        )

        # Delete client
        await db.execute(
            delete(Client).where(Client.id == user.client_id)
        )

        print(f"  Deleted: {user.email}")

    await db.commit()
    print("Reset complete.")


async def main(reset: bool = False):
    """Main seed function."""
    print("=" * 60)
    print("Test Client Seed Script")
    print("=" * 60)

    async with async_session_factory() as db:
        if reset:
            await reset_test_clients(db)

        # Get all tenants
        tenants = await get_all_tenants(db)
        print(f"\nFound {len(tenants)} tenants:")
        for t in tenants:
            print(f"  - {t.name} ({t.slug})")

        # Create clients for each configured tenant
        created_clients = []

        for tenant_slug, clients_data in TEST_CLIENTS.items():
            tenant = await get_tenant_by_slug(db, tenant_slug)

            if not tenant:
                print(f"\n  WARNING: Tenant '{tenant_slug}' not found, skipping...")
                continue

            print(f"\n  Creating clients for tenant: {tenant.name}")

            # Show tenant's enabled modules
            enabled_modules = await get_tenant_enabled_modules(db, tenant.id)
            print(f"    Tenant enabled modules: {[m.code for m in enabled_modules]}")

            for client_data in clients_data:
                client = await create_client_with_modules(db, tenant, client_data)
                if client:
                    created_clients.append({
                        "tenant": tenant.name,
                        "email": client_data["email"],
                        "password": client_data["password"],
                        "disabled_modules": client_data.get("disabled_modules", []),
                    })

    print("\n" + "=" * 60)
    print("Seed complete!")
    print("=" * 60)

    if created_clients:
        print("\nTest credentials created:")
        for c in created_clients:
            print(f"\n  Tenant: {c['tenant']}")
            print(f"  Email: {c['email']}")
            print(f"  Password: {c['password']}")
            if c['disabled_modules']:
                print(f"  Disabled modules: {c['disabled_modules']}")
            else:
                print(f"  Access: All tenant modules")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed test client accounts")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset existing test clients before seeding",
    )
    args = parser.parse_args()

    asyncio.run(main(reset=args.reset))
