from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.core.context import set_context
from src.core.security import decode_token

class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, 
        app: ASGIApp,
    ):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. 获取或生成 Request ID
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        
        # 2. 构建基础上下文
        ctx = {
            "request_id": request_id,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        # 3. 尝试解析 Token 获取用户信息
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                # 注意：这里不验证 Token 的有效性（交给依赖项处理），只提取信息
                # 如果 decode_token 内部有严格验证且抛出异常，这里捕获并忽略
                payload = decode_token(token)
                if payload:
                    ctx["user_id"] = payload.sub
                    ctx["tenant_id"] = payload.tenant_id
                    ctx["roles"] = payload.roles
                    ctx["user_type"] = payload.user_type
            except Exception:
                # Token 解析失败（过期、格式错误等），忽略，保持匿名上下文
                pass

        # 4. 设置 ContextVar
        set_context(ctx)

        # 5. 执行后续处理
        response = await call_next(request)

        # 6. 添加响应头
        response.headers["X-Request-Id"] = request_id
        
        return response
