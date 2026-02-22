import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from src.api.deps import get_current_tenant_admin, get_current_user
from src.main import app
from src.models.audit_log import AuditLog
from src.models.tenant import Tenant
from src.models.user import User


@pytest.mark.asyncio
async def test_list_audit_logs_scoped_to_tenant(client: AsyncClient, db_session, test_tenant_id, test_user_id):
    other_tenant_id = "00000000-0000-0000-0000-000000000003"

    log1 = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        event_type="user",
        level="info",
        category="security",
        resource_type="user",
        resource_id=str(uuid.uuid4()),
        action="create",
        outcome="success",
        user_id=test_user_id,
        user_email="admin@example.com",
        created_at=datetime.now(timezone.utc),
    )
    log2 = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=other_tenant_id,
        event_type="user",
        level="info",
        category="security",
        resource_type="user",
        resource_id=str(uuid.uuid4()),
        action="update",
        outcome="success",
        user_id=test_user_id,
        user_email="other@example.com",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([log1, log2])
    await db_session.commit()

    async def override_get_current_user():
        return {
            "user_id": test_user_id,
            "tenant_id": test_tenant_id,
            "roles": ["tenant_admin"],
            "email": "admin@example.com",
        }

    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        response = await client.get("/api/v1/audit-logs/?skip=0&limit=50")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["tenant_id"] == test_tenant_id
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_audit_logs_scoped_to_team_for_supervisor(client: AsyncClient, db_session, test_tenant_id):
    supervisor_id = "00000000-0000-0000-0000-000000000010"
    subordinate_id = "00000000-0000-0000-0000-000000000011"
    peer_id = "00000000-0000-0000-0000-000000000012"

    tenant = Tenant(id=test_tenant_id, name="Tenant A", slug="tenant-a", is_active=True)
    db_session.add(tenant)

    supervisor = User(
        id=supervisor_id,
        tenant_id=test_tenant_id,
        email="supervisor@example.com",
        first_name="Supervisor",
        last_name="User",
        is_active=True,
    )
    subordinate = User(
        id=subordinate_id,
        tenant_id=test_tenant_id,
        email="subordinate@example.com",
        first_name="Subordinate",
        last_name="User",
        is_active=True,
        supervisor_id=supervisor_id,
    )
    peer = User(
        id=peer_id,
        tenant_id=test_tenant_id,
        email="peer@example.com",
        first_name="Peer",
        last_name="User",
        is_active=True,
    )
    db_session.add_all([supervisor, subordinate, peer])
    await db_session.commit()

    log_supervisor = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        event_type="user",
        level="info",
        category="security",
        resource_type="user",
        resource_id=str(uuid.uuid4()),
        action="update",
        outcome="success",
        user_id=supervisor_id,
        user_email="supervisor@example.com",
        created_at=datetime.now(timezone.utc),
    )
    log_subordinate = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        event_type="client",
        level="info",
        category="security",
        resource_type="client",
        resource_id=str(uuid.uuid4()),
        action="create",
        outcome="success",
        user_id=subordinate_id,
        user_email="subordinate@example.com",
        created_at=datetime.now(timezone.utc),
    )
    log_peer = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=test_tenant_id,
        event_type="client",
        level="info",
        category="security",
        resource_type="client",
        resource_id=str(uuid.uuid4()),
        action="delete",
        outcome="success",
        user_id=peer_id,
        user_email="peer@example.com",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([log_supervisor, log_subordinate, log_peer])
    await db_session.commit()

    async def override_get_current_user():
        return {
            "user_id": supervisor_id,
            "tenant_id": test_tenant_id,
            "roles": ["eam_supervisor"],
            "email": "supervisor@example.com",
        }

    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        response = await client.get("/api/v1/audit-logs/?skip=0&limit=50")
        assert response.status_code == 200
        payload = response.json()
        returned_user_ids = {item["user_id"] for item in payload["items"]}
        assert payload["total"] == 2
        assert returned_user_ids == {supervisor_id, subordinate_id}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_team_tree_denies_cross_tenant_for_supervisor(client: AsyncClient, db_session):
    tenant_a_id = "00000000-0000-0000-0000-000000000020"
    tenant_b_id = "00000000-0000-0000-0000-000000000021"
    supervisor_id = "00000000-0000-0000-0000-000000000022"
    other_user_id = "00000000-0000-0000-0000-000000000023"

    tenant_a = Tenant(id=tenant_a_id, name="Tenant A", slug="tenant-a", is_active=True)
    tenant_b = Tenant(id=tenant_b_id, name="Tenant B", slug="tenant-b", is_active=True)
    db_session.add_all([tenant_a, tenant_b])

    supervisor = User(
        id=supervisor_id,
        tenant_id=tenant_a_id,
        email="supervisor-a@example.com",
        first_name="Supervisor",
        last_name="A",
        is_active=True,
    )
    other_user = User(
        id=other_user_id,
        tenant_id=tenant_b_id,
        email="user-b@example.com",
        first_name="User",
        last_name="B",
        is_active=True,
    )
    db_session.add_all([supervisor, other_user])
    await db_session.commit()

    async def override_get_current_user():
        return {
            "user_id": supervisor_id,
            "tenant_id": tenant_a_id,
            "roles": ["eam_supervisor"],
            "email": "supervisor-a@example.com",
        }

    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        response = await client.get(f"/api/v1/users/{other_user_id}/team-tree")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_audit_log(client: AsyncClient, db_session, test_tenant_id, test_user_id):
    async def override_get_current_tenant_admin():
        return {
            "user_id": test_user_id,
            "tenant_id": test_tenant_id,
            "roles": ["tenant_admin"],
            "email": "admin@example.com",
        }

    app.dependency_overrides[get_current_tenant_admin] = override_get_current_tenant_admin
    try:
        payload = {
            "event_type": "user",
            "level": "info",
            "category": "security",
            "resource_type": "user",
            "resource_id": str(uuid.uuid4()),
            "action": "create",
            "outcome": "success",
            "new_value": {"email": "new@example.com"},
        }
        response = await client.post("/api/v1/audit-logs/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == test_tenant_id
        assert data["event_type"] == "user"
        assert data["new_value"]["email"] == "new@example.com"
    finally:
        app.dependency_overrides.pop(get_current_tenant_admin, None)
