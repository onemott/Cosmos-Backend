import pytest
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from src.models.chat import ChatSession, ChatMessage
from src.models.client import Client
from src.models.tenant import Tenant

@pytest.mark.asyncio
async def test_message_deduplication(db_session):
    """Test unique constraint on client_side_id."""
    # 1. Setup Tenant and Client
    tenant_id = str(uuid4())
    tenant = Tenant(id=tenant_id, name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    
    client_id = str(uuid4())
    client = Client(id=client_id, tenant_id=tenant_id, first_name="Test", last_name="Client")
    db_session.add(client)
    
    session_id = str(uuid4())
    chat_session = ChatSession(id=session_id, client_id=client_id)
    db_session.add(chat_session)
    
    await db_session.commit()
    
    # 2. Insert first message
    msg_id_1 = str(uuid4())
    client_side_id = "unique-client-id-123"
    msg1 = ChatMessage(
        id=msg_id_1,
        session_id=session_id,
        client_side_id=client_side_id,
        sender_type="client_user",
        sender_id="user-123",
        content="Hello",
        message_type="text"
    )
    db_session.add(msg1)
    await db_session.commit()
    
    # 3. Try insert duplicate message
    msg_id_2 = str(uuid4())
    msg2 = ChatMessage(
        id=msg_id_2,
        session_id=session_id,
        client_side_id=client_side_id, # Duplicate
        sender_type="client_user",
        sender_id="user-123",
        content="Hello again",
        message_type="text"
    )
    db_session.add(msg2)
    
    with pytest.raises(IntegrityError):
        await db_session.commit()
        
    await db_session.rollback()

@pytest.mark.asyncio
async def test_cascade_delete(db_session):
    """Test cascade delete from Client -> ChatSession -> ChatMessage."""
    # 1. Setup
    tenant_id = str(uuid4())
    tenant = Tenant(id=tenant_id, name="Test Tenant 2", slug="test-tenant-2")
    db_session.add(tenant)
    
    client_id = str(uuid4())
    client = Client(id=client_id, tenant_id=tenant_id, first_name="Test", last_name="Client")
    db_session.add(client)
    
    session_id = str(uuid4())
    chat_session = ChatSession(id=session_id, client_id=client_id)
    db_session.add(chat_session)
    await db_session.commit()
    
    # Add message
    msg_id = str(uuid4())
    msg = ChatMessage(
        id=msg_id,
        session_id=session_id,
        sender_type="system",
        sender_id="system",
        content="Welcome"
    )
    db_session.add(msg)
    await db_session.commit()
    
    # 2. Delete Client
    await db_session.delete(client)
    await db_session.commit()
    
    # 3. Verify Session and Message are gone
    result = await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    assert result.scalar_one_or_none() is None
    
    result = await db_session.execute(select(ChatMessage).where(ChatMessage.session_id == session_id))
    assert result.scalar_one_or_none() is None
