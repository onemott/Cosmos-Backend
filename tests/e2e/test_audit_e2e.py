import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog
from src.core.context import get_context
from src.api.deps import get_current_user

# 测试用的模拟用户数据
MOCK_USER = {
    "user_id": "test-user-id",
    "tenant_id": "test-tenant-id",
    "roles": ["tenant_admin"],
    "email": "test@example.com"
}

from unittest.mock import patch
from sqlalchemy.ext.asyncio import async_sessionmaker

@pytest.mark.asyncio
async def test_audit_logging_e2e(client: AsyncClient, db_session: AsyncSession, async_engine):
    """
    端到端验证自动化审计日志功能：
    1. 模拟登录用户。
    2. 发起 POST 请求创建资源（User）。
    3. 验证是否自动生成了 Insert 类型的审计日志。
    4. 验证日志内容是否包含正确的 user_id, tenant_id 和 new_value。
    """
    
    # 0. 确保监听器已注册（因为测试环境可能未触发 lifespan）
    from src.db.audit_listener import register_audit_listeners
    from src.models import User
    register_audit_listeners([User])
    
    # Patch async_session_factory to use test engine
    test_session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # 1. 覆盖 get_current_user 依赖，模拟已登录用户
    from src.main import app
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    
    # Mock decode_token to return valid payload for middleware
    from unittest.mock import MagicMock
    mock_payload = MagicMock()
    mock_payload.sub = MOCK_USER["user_id"]
    mock_payload.tenant_id = MOCK_USER["tenant_id"]
    mock_payload.roles = MOCK_USER["roles"]
    mock_payload.user_type = "staff"
    
    with patch("src.services.audit_log_service.async_session_factory", test_session_factory), \
         patch("src.middleware.request_context.decode_token", return_value=mock_payload):
        # 2. 发送创建 User 的请求
        user_data = {
            "email": "newuser@example.com",
            "password": "StrongPassword123!",
            "first_name": "New",
            "last_name": "User",
            "tenant_id": "test-tenant-id",
            "role_ids": [] 
        }
        
        response = await client.post(
            "/api/v1/users/",
            json=user_data,
            headers={"Authorization": "Bearer mock-token"} 
        )
        
        if response.status_code != 201:
            print(f"API Error: {response.status_code} {response.text}")
            
        # 3. 验证审计日志
        import asyncio
        await asyncio.sleep(0.5) # 增加等待时间确保异步任务完成
        
        # 提交当前会话事务
        await db_session.commit()
        
        # 查询 AuditLog
        result = await db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.resource_type == "users",
                AuditLog.event_type == "entity_change"
            )
            .order_by(AuditLog.created_at.desc())
        )
        logs = result.scalars().all()
        
        # 4. 断言
        assert len(logs) > 0, "未找到自动生成的审计日志 (entity_change)"
        
        log = logs[0]
        assert log.action == "create"
        assert log.user_id == MOCK_USER["user_id"]
        assert log.tenant_id == MOCK_USER["tenant_id"]
        assert log.new_value["email"] == user_data["email"]
        # 敏感字段应被脱敏
        if "hashed_password" in log.new_value:
            assert log.new_value["hashed_password"] == "***"
        if "password" in log.new_value:
            assert log.new_value["password"] == "***"

        print("\n✅ E2E Audit Log Verified!")
        print(f"   ID: {log.id}")
        print(f"   Action: {log.action}")
        print(f"   Event Type: {log.event_type}")
        print(f"   User: {log.user_id}")
        print(f"   Resource: {log.resource_type}/{log.resource_id}")

