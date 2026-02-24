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

import argparse
import asyncio
from decimal import Decimal
import sys
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.account import Account, AccountType
from src.models.audit_log import AuditLog
from src.models.client import Client, ClientType, KYCStatus, RiskProfile
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
    query = select(Tenant).where(Tenant.slug.in_(["test-firm", "test-firm-role-demo"]))
    result = await session.execute(query)
    tenant = result.scalar_one_or_none()

    if not tenant:
        fallback_query = select(Tenant).where(Tenant.slug.like("%test%"))
        fallback_result = await session.execute(fallback_query)
        tenant = fallback_result.scalars().first()

    if tenant:
        print(f"✅ Using existing test tenant: {tenant.name}")
        return tenant

    tenant = Tenant(
        id=str(uuid4()),
        name="Test EAM Firm",
        slug="test-firm",
        contact_email="contact@test-firm.com",
        is_active=True,
        settings={"description": "Test tenant for role hierarchy demonstration"},
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
            tenant_id=tenant.id if tenant else None,
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


async def get_user_by_email(session, email: str) -> User | None:
    query = select(User).where(User.email == email)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_client_by_email(session, email: str) -> Client | None:
    query = select(Client).where(Client.email == email)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def seed_team_clients(session, tenant: Tenant, users_by_role: dict[str, User]) -> None:
    demo_clients = [
        {
            "email": "delta.admin@testfirm.com",
            "first_name": "Delta",
            "last_name": "AdminClient",
            "assigned_role": "tenant_admin",
            "risk_profile": RiskProfile.BALANCED,
            "total_value": Decimal("2000000"),
        },
        {
            "email": "alpha.supervisor@testfirm.com",
            "first_name": "Alpha",
            "last_name": "SupervisorClient",
            "assigned_role": "eam_supervisor",
            "risk_profile": RiskProfile.GROWTH,
            "total_value": Decimal("1200000"),
        },
        {
            "email": "beta.supervisor@testfirm.com",
            "first_name": "Beta",
            "last_name": "SupervisorClient",
            "assigned_role": "eam_supervisor",
            "risk_profile": RiskProfile.MODERATE,
            "total_value": Decimal("850000"),
        },
        {
            "email": "gamma.staff@testfirm.com",
            "first_name": "Gamma",
            "last_name": "StaffClient",
            "assigned_role": "eam_staff",
            "risk_profile": RiskProfile.CONSERVATIVE,
            "total_value": Decimal("300000"),
        },
    ]

    tenant_admin = users_by_role.get("tenant_admin")

    for client_data in demo_clients:
        assigned_user = users_by_role.get(client_data["assigned_role"])
        if not assigned_user:
            print(f"  ⚠️  Missing user for role {client_data['assigned_role']}, skipping client")
            continue

        existing_client = await get_client_by_email(session, client_data["email"])
        if existing_client:
            existing_client.assigned_to_user_id = assigned_user.id
            if tenant_admin:
                existing_client.created_by_user_id = tenant_admin.id
            print(f"  ⚠️  Client {client_data['email']} already exists, updating assignment...")
            client = existing_client
        else:
            client = Client(
                id=str(uuid4()),
                tenant_id=tenant.id,
                client_type=ClientType.INDIVIDUAL,
                first_name=client_data["first_name"],
                last_name=client_data["last_name"],
                email=client_data["email"],
                kyc_status=KYCStatus.APPROVED,
                risk_profile=client_data["risk_profile"],
                assigned_to_user_id=assigned_user.id,
                created_by_user_id=tenant_admin.id if tenant_admin else assigned_user.id,
            )
            session.add(client)
            await session.flush()
            print(f"  👥 Created demo client: {client.email} -> {assigned_user.email}")

        account_name = f"{client.first_name} {client.last_name} Portfolio"
        account_result = await session.execute(
            select(Account).where(
                Account.client_id == client.id,
                Account.account_name == account_name,
            )
        )
        existing_account = account_result.scalar_one_or_none()
        if existing_account:
            existing_account.total_value = client_data["total_value"]
            existing_account.cash_balance = (
                client_data["total_value"] * Decimal("0.1")
            ).quantize(Decimal("0.01"))
        else:
            account = Account(
                id=str(uuid4()),
                tenant_id=tenant.id,
                client_id=client.id,
                account_number=f"DEMO-{uuid4().hex[:10]}",
                account_name=account_name,
                account_type=AccountType.INVESTMENT,
                currency="USD",
                total_value=client_data["total_value"],
                cash_balance=(client_data["total_value"] * Decimal("0.1")).quantize(Decimal("0.01")),
            )
            session.add(account)


async def seed_audit_logs(
    session,
    tenant: Tenant,
    user: User | None,
    event_source: str,
) -> None:
    existing = await session.execute(
        select(AuditLog).where(
            AuditLog.request_id == "demo-seed",
            AuditLog.tenant_id == tenant.id,
            AuditLog.event_type.like(f"{event_source}.%"),
        )
    )
    if existing.scalars().first():
        print("  ⚠️  Demo audit logs already exist, skipping...")
        return

    user_id = str(user.id) if user else None
    user_email = user.email if user else None

    events = [
        ("auth.login", "security", "session", "login", "success"),
        ("team.view", "analytics", "team", "read", "success"),
        ("client.create", "client", "client", "create", "success"),
        ("client.assign", "client", "client", "assign", "success"),
        ("user.update", "user", "user", "update", "success"),
        ("audit.export", "security", "audit_log", "export", "success"),
    ]

    for event_type, category, resource_type, action, outcome in events:
        log = AuditLog(
            tenant_id=tenant.id,
            event_type=f"{event_source}.{event_type}",
            level="info",
            category=category,
            resource_type=resource_type,
            resource_id=None,
            action=action,
            outcome=outcome,
            user_id=user_id,
            user_email=user_email,
            ip_address="127.0.0.1",
            user_agent="seed-script",
            request_id="demo-seed",
            extra_data={"seeded": True, "source": event_source},
            tags=["demo_seed"],
        )
        session.add(log)


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
            users_by_role: dict[str, User] = {}
            
            # Create users for each role
            for role_name, user_data in TEST_USERS.items():
                print(f"\n📋 Creating account for role: {role_name}")
                
                # Determine which tenant to use
                if role_name in ["super_admin", "platform_admin", "platform_user"]:
                    tenant = None
                    print(f"  Using NO tenant (Platform)")
                else:
                    tenant = test_tenant
                    print(f"  Using test EAM tenant")
                
                user = await create_user_with_role(session, role_name, user_data, tenant)
                if user:
                    created_users.append({
                        "role": role_name,
                        "email": user_data["email"],
                        "password": user_data["password"],
                        "tenant": tenant.name if tenant else "Platform",
                        "name": f"{user_data['first_name']} {user_data['last_name']}"
                    })
                    users_by_role[role_name] = user

            await seed_team_clients(session, test_tenant, users_by_role)
            await seed_audit_logs(session, test_tenant, users_by_role.get("tenant_admin"), "tenant")
            await seed_audit_logs(session, platform_tenant, users_by_role.get("platform_admin"), "platform")
            
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
    parser = argparse.ArgumentParser(description="Seed role accounts and demo data")
    parser.parse_args()
    print("🚀 Starting Role Account Seeding...")
    print("")
    asyncio.run(seed_role_accounts())
