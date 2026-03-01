import logging
from typing import Dict, Any, List

from sqlalchemy import event, inspect
from sqlalchemy.orm import Mapper, object_mapper
from sqlalchemy.orm.attributes import get_history

from src.core.context import get_context
from src.services.audit_log_service import enqueue_audit_log

logger = logging.getLogger(__name__)

def get_audit_context() -> Dict[str, Any]:
    """从当前上下文中提取审计所需信息"""
    ctx = get_context()
    return {
        "user_id": ctx.get("user_id"),
        "tenant_id": ctx.get("tenant_id"),
        "ip_address": ctx.get("ip_address"),
        "user_agent": ctx.get("user_agent"),
        "request_id": ctx.get("request_id"),
    }

def model_to_dict(obj: Any) -> Dict[str, Any]:
    """将模型实例转换为字典"""
    if not obj:
        return {}
    try:
        mapper = object_mapper(obj)
        return {
            c.key: getattr(obj, c.key)
            for c in mapper.column_attrs
        }
    except Exception:
        return {}

def audit_insert(mapper: Mapper, connection, target: Any):
    """处理插入事件"""
    try:
        # 避免审计日志本身被审计，防止死循环
        if target.__tablename__ in ["audit_logs", "audit_log_archives"]:
            return
            
        print(f"DEBUG: audit_insert triggered for {target.__tablename__}")

        context = get_audit_context()
        new_value = model_to_dict(target)
        
        # 尝试从 target 中获取 tenant_id，如果 context 中没有
        tenant_id = context.get("tenant_id")
        if not tenant_id and hasattr(target, "tenant_id"):
            tenant_id = str(target.tenant_id) if target.tenant_id else None

        log_data = {
            "tenant_id": tenant_id,
            "event_type": "entity_change",
            "category": "audit",
            "resource_type": target.__tablename__,
            "resource_id": str(getattr(target, "id", "")),
            "action": "create",
            "outcome": "success",
            "new_value": new_value,
            **context
        }
        
        # 如果 context 中有 tenant_id，优先使用 context 中的，否则使用 target 中的
        # 上面的 **context 会覆盖 log_data 中的同名键，所以这里需要重新确认 tenant_id
        if tenant_id:
            log_data["tenant_id"] = tenant_id

        enqueue_audit_log(log_data)
        print(f"DEBUG: Enqueued audit log for {target.__tablename__}")
    except Exception as e:
        logger.error(f"Error in audit_insert: {e}")
        print(f"DEBUG: Error in audit_insert: {e}")

def audit_update(mapper: Mapper, connection, target: Any):
    """处理更新事件"""
    try:
        if target.__tablename__ in ["audit_logs", "audit_log_archives"]:
            return

        context = get_audit_context()
        
        # 计算变更字段
        state = inspect(target)
        old_value = {}
        new_value = {}
        changes_found = False

        for attr in mapper.column_attrs:
            hist = get_history(target, attr.key)
            if hist.has_changes():
                changes_found = True
                # hist.deleted 包含旧值 (tuple)，取第一个
                old_val = hist.deleted[0] if hist.deleted else None
                # hist.added 包含新值 (tuple)，取第一个
                new_val = hist.added[0] if hist.added else None
                
                old_value[attr.key] = old_val
                new_value[attr.key] = new_val

        if not changes_found:
            return

        tenant_id = context.get("tenant_id")
        if not tenant_id and hasattr(target, "tenant_id"):
            tenant_id = str(target.tenant_id) if target.tenant_id else None

        log_data = {
            "tenant_id": tenant_id,
            "event_type": "entity_change",
            "category": "audit",
            "resource_type": target.__tablename__,
            "resource_id": str(getattr(target, "id", "")),
            "action": "update",
            "outcome": "success",
            "old_value": old_value,
            "new_value": new_value,
            **context
        }

        if tenant_id:
            log_data["tenant_id"] = tenant_id

        enqueue_audit_log(log_data)
    except Exception as e:
        logger.error(f"Error in audit_update: {e}")

def audit_delete(mapper: Mapper, connection, target: Any):
    """处理删除事件"""
    try:
        if target.__tablename__ in ["audit_logs", "audit_log_archives"]:
            return

        context = get_audit_context()
        old_value = model_to_dict(target)

        tenant_id = context.get("tenant_id")
        if not tenant_id and hasattr(target, "tenant_id"):
            tenant_id = str(target.tenant_id) if target.tenant_id else None

        log_data = {
            "tenant_id": tenant_id,
            "event_type": "entity_change",
            "category": "audit",
            "resource_type": target.__tablename__,
            "resource_id": str(getattr(target, "id", "")),
            "action": "delete",
            "outcome": "success",
            "old_value": old_value,
            **context
        }

        if tenant_id:
            log_data["tenant_id"] = tenant_id

        enqueue_audit_log(log_data)
    except Exception as e:
        logger.error(f"Error in audit_delete: {e}")

def register_audit_listeners(models: List[Any]):
    """注册审计监听器"""
    for model in models:
        event.listen(model, "after_insert", audit_insert)
        event.listen(model, "after_update", audit_update)
        event.listen(model, "after_delete", audit_delete)
        logger.info(f"Registered audit listener for {model.__tablename__}")
