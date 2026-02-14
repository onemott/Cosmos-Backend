import pytest
import uuid
from httpx import AsyncClient
from src.models.task import Task, TaskStatus, TaskPriority, TaskType, WorkflowState
from datetime import datetime, timezone

@pytest.mark.asyncio
async def test_list_tasks_pagination(client: AsyncClient, db_session, test_tenant_id, test_user_id):
    """Test pagination for listing tasks."""
    # 1. Setup: Create test client and tasks
    # Assume client_id is "test_client_id" (needs to match what get_current_client returns or uses)
    # Based on conftest.py, we might need to know how authentication is handled.
    # However, since we are using client fixture which overrides get_db, 
    # we also need to override get_current_client or ensure the test client is authenticated.
    # For simplicity, let's assume the default behavior or mock get_current_client if needed.
    
    # Actually, looking at src/api/deps.py would be ideal to see how get_current_client works.
    # But for now, let's assume we can inject a mock or rely on a standard test user.
    # The list_tasks endpoint uses `current_client: dict = Depends(get_current_client)`.
    # We should override this dependency to bypass auth and return a fixed client_id.
    
    client_id = str(uuid.uuid4())
    
    from src.api.deps import get_current_client
    from src.main import app
    
    async def override_get_current_client():
        return {
            "client_id": client_id,
            "tenant_id": test_tenant_id,
            "user_id": test_user_id,
            "email": "test@example.com"
        }
        
    app.dependency_overrides[get_current_client] = override_get_current_client
    
    try:
        # Create 25 tasks
        tasks = []
        for i in range(25):
            task = Task(
                id=str(uuid.uuid4()),
                title=f"Task {i}",
                description=f"Description {i}",
                status=TaskStatus.PENDING,
                priority=TaskPriority.MEDIUM,
                task_type=TaskType.GENERAL,
                client_id=client_id,
                tenant_id=test_tenant_id,
                created_by_id=test_user_id,
                created_at=datetime.now(timezone.utc),
                workflow_state=WorkflowState.PENDING_CLIENT
            )
            db_session.add(task)
        await db_session.commit()
        
        # 2. Act: Request first page (limit=10)
        # Note: The router prefix in client_tasks.py is "/client/tasks"
        # And in main.py it's included under "/api/v1"
        # So the full path is "/api/v1/client/tasks"
        response_page1 = await client.get("/api/v1/client/tasks?skip=0&limit=10")
        if response_page1.status_code != 200:
             print(f"Error Response: {response_page1.text}")
        assert response_page1.status_code == 200
        data_page1 = response_page1.json()
        assert len(data_page1["tasks"]) == 10
        
        # 3. Act: Request second page (skip=10, limit=10)
        response_page2 = await client.get("/api/v1/client/tasks?skip=10&limit=10")
        assert response_page2.status_code == 200
        data_page2 = response_page2.json()
        assert len(data_page2["tasks"]) == 10
        
        # 4. Act: Request third page (skip=20, limit=10) -> should return 5
        response_page3 = await client.get("/api/v1/client/tasks?skip=20&limit=10")
        assert response_page3.status_code == 200
        data_page3 = response_page3.json()
        assert len(data_page3["tasks"]) == 5
        
        # 5. Verify: Ensure pages are distinct
        ids_page1 = {t['id'] for t in data_page1["tasks"]}
        ids_page2 = {t['id'] for t in data_page2["tasks"]}
        ids_page3 = {t['id'] for t in data_page3["tasks"]}
        
        assert ids_page1.isdisjoint(ids_page2)
        assert ids_page2.isdisjoint(ids_page3)
        
    finally:
        app.dependency_overrides.pop(get_current_client, None)
