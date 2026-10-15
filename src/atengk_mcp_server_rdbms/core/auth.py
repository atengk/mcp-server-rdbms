"""
mcp-server-rdbms: HTTP 传输层 Bearer Token 访问令牌安全认证中间件.

@author Ateng
@since 2026-10-15
"""

import hmac
from typing import ClassVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """HTTP 传输层令牌门禁中间件：校验 Bearer Token 或 Query 认证参数，时序安全防篡改.

    @author Ateng
    @since 2026-10-15
    """

    UNAUTHORIZED_BODY: ClassVar[dict[str, str]] = {
        "error": "Unauthorized",
        "message": "无效或缺失的访问令牌 (Invalid or missing Bearer token)",
    }

    PUBLIC_PATHS: ClassVar[set[str]] = {"/health", "/ping"}

    def __init__(self, app: object, token: str) -> None:
        """初始化令牌认证中间件.

        @param app: ASGI/Starlette 目标应用实例
        @param token: 预设的标准合规访问令牌明文
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._token = token.strip()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """拦截请求并执行时序安全的令牌一致性校验.

        放行策略：
        1. OPTIONS 预检请求：浏览器 CORS Preflight 免认证穿透放行；
        2. 公开探针端点：/health 与 /ping 路径免密放行（供云原生探活）；
        3. 标准业务请求：必须携带有效 Bearer Token 或 Query 认证参数。

        支持两类凭据传递通道：
        1. 标准 Authorization 头部: `Authorization: Bearer <token>`
        2. Query 查询参数 (EventSource/SSE 客户端友好): `?token=<token>` 或 `?auth_token=<token>`

        @param request: Starlette 请求对象
        @param call_next: 下游请求处理器
        @return: 认证通过时返回正常响应，未认证时返回 401 Unauthorized
        """
        # 1. 跨域预检请求 (CORS Preflight) 免认证穿透放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2. 公开健康探针与心跳端点免密放行
        if request.url.path.rstrip("/") in self.PUBLIC_PATHS:
            return await call_next(request)

        candidate_token: str | None = None

        # 1. 优先提取标准 Authorization 头部
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            candidate_token = auth_header[7:].strip()

        # 2. 兜底提取 URL Query 查询参数（针对浏览器原生 EventSource 缺少自定义 Header 场景）
        if not candidate_token:
            candidate_token = (
                request.query_params.get("token")
                or request.query_params.get("auth_token")
            )

        # 3. 使用 hmac.compare_digest 防御时序侧信道攻击 (Timing Attack)
        if candidate_token and hmac.compare_digest(candidate_token, self._token):
            return await call_next(request)

        return JSONResponse(
            self.UNAUTHORIZED_BODY,
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
