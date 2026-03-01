from contextvars import ContextVar
from typing import Dict, Any, Optional

# 定义上下文变量，默认为空字典
request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})

def set_context(context: Dict[str, Any]) -> None:
    """
    设置当前请求的上下文信息。
    通常在中间件或依赖项中调用。
    """
    request_context.set(context)

def get_context() -> Dict[str, Any]:
    """
    获取当前请求的上下文信息。
    如果未设置，返回空字典。
    """
    return request_context.get()

def update_context(**kwargs: Any) -> None:
    """
    更新当前上下文中的特定字段。
    """
    ctx = request_context.get().copy()
    ctx.update(kwargs)
    request_context.set(ctx)

def get_context_value(key: str, default: Any = None) -> Any:
    """
    获取上下文中的特定值。
    """
    return request_context.get().get(key, default)
