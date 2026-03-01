import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime, timezone

from src.models.tenant import Tenant
from src.models.client import Client
from src.models.client_user import ClientUser
from src.models.user import User
from src.models.chat import ChatSession, ChatMessage
from src.services.chat_service import ChatService
from src.api.deps import get_current_client, require_tenant_user
from src.main import app

@pytest.mark.asyncio
async def test_chat_api_flow(client: AsyncClient, db_session, test_tenant_id, test_user_id):
    """Test Chat HTTP API flow for both Client and Admin."""
    
    # 1. Setup Data
    # Tenant
    tenant = Tenant(id=test_tenant_id, name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    
    # Advisor User
    advisor = User(
        id=test_user_id, 
        tenant_id=test_tenant_id, 
        email="advisor@test.com", 
        hashed_password="hash", 
        first_name="Test", 
        last_name="Advisor", 
        is_active=True
    )
    db_session.add(advisor)
    
    # Client
    client_id = str(uuid4())
    client_obj = Client(
        id=client_id, 
        tenant_id=test_tenant_id, 
        first_name="Test", 
        last_name="Client",
        assigned_to_user_id=test_user_id
    )
    db_session.add(client_obj)
    
    # Client User
    client_user_id = str(uuid4())
    client_user = ClientUser(
        id=client_user_id,
        client_id=client_id,
        tenant_id=test_tenant_id,
        email="client@test.com",
        hashed_password="hash",
        is_active=True
    )
    db_session.add(client_user)
    
    await db_session.commit()
    
    # 2. Simulate Chat Activity (via Service)
    chat_service = ChatService(db_session)
    
    # Client creates session (simulated)
    session = await chat_service.create_or_get_session(client_id, client_user_id, "client_user")
    
    # Client sends message
    msg1 = await chat_service.save_message(
        session_id=session.id,
        sender_type="client_user",
        sender_id=client_user_id,
        content="Hello Advisor",
        client_side_id="msg-1"
    )
    
    # Advisor replies
    msg2 = await chat_service.save_message(
        session_id=session.id,
        sender_type="user",
        sender_id=test_user_id,
        content="Hello Client",
        client_side_id="msg-2"
    )
    
    # 3. Test Client API: List Sessions
    # Mock Auth for Client
    async def mock_get_current_client():
        return {
            "client_user_id": client_user_id,
            "client_id": client_id,
            "tenant_id": test_tenant_id,
            "user_type": "client",
            "roles": ["client"],
            "email": "client@test.com"
        }
    app.dependency_overrides[get_current_client] = mock_get_current_client
    
    response = await client.get("/api/v1/client/chat/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == session.id
    assert data[0]["last_message"] == "Hello Client"
    assert data[0]["unread_count"] == 2 # Never read
    
    # 4. Test Client API: Get History
    response = await client.get(f"/api/v1/client/chat/sessions/{session.id}/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    assert history[0]["content"] == "Hello Client" # desc order
    
    # 5. Test Client API: Mark Read
    response = await client.post(f"/api/v1/client/chat/sessions/{session.id}/read")
    assert response.status_code == 200
    
    # Verify unread count is 0
    response = await client.get("/api/v1/client/chat/sessions")
    data = response.json()
    assert data[0]["unread_count"] == 0
    
    app.dependency_overrides.pop(get_current_client)
    
    # 6. Test Admin API: List Sessions
    # Mock Auth for Admin
    async def mock_require_tenant_user():
        return {
            "user_id": test_user_id,
            "tenant_id": test_tenant_id,
            "roles": ["advisor"],
            "user_type": "user"
        }
    app.dependency_overrides[require_tenant_user] = mock_require_tenant_user
    
    response = await client.get("/api/v1/chat/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["client_id"] == client_id
    
    # 7. Test Admin API: Get History
    response = await client.get(f"/api/v1/chat/sessions/{session.id}/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    
    app.dependency_overrides.pop(require_tenant_user)
