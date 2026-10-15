"""
mcp-server-rdbms: HTTP 传输层访问令牌认证中间件与安全门禁测试.

@author Ateng
@since 2026-10-15
"""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from atengk_mcp_server_rdbms.cli import parse_args
from atengk_mcp_server_rdbms.core.auth import TokenAuthMiddleware
from atengk_mcp_server_rdbms.core.env import resolve_runtime_config


def _dummy_endpoint(request: Request):
    return PlainTextResponse("authenticated")


def _create_app(token: str) -> Starlette:
    app = Starlette(routes=[Route("/test", endpoint=_dummy_endpoint)])
    app.add_middleware(TokenAuthMiddleware, token=token)
    return app


def test_token_auth_middleware_missing_token():
    app = _create_app("secret-token-888")
    client = TestClient(app)

    resp = client.get("/test")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"
    data = resp.json()
    assert data["error"] == "Unauthorized"
    assert "无效或缺失" in data["message"]


def test_token_auth_middleware_wrong_header_token():
    app = _create_app("secret-token-888")
    client = TestClient(app)

    resp = client.get("/test", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "Unauthorized"


def test_token_auth_middleware_valid_header_token():
    app = _create_app("secret-token-888")
    client = TestClient(app)

    resp = client.get("/test", headers={"Authorization": "Bearer secret-token-888"})
    assert resp.status_code == 200
    assert resp.text == "authenticated"


def test_token_auth_middleware_wrong_query_token():
    app = _create_app("secret-token-888")
    client = TestClient(app)

    resp = client.get("/test?token=wrong-token")
    assert resp.status_code == 401

    resp2 = client.get("/test?auth_token=wrong-token")
    assert resp2.status_code == 401


def test_token_auth_middleware_valid_query_token():
    app = _create_app("secret-token-888")
    client = TestClient(app)

    resp = client.get("/test?token=secret-token-888")
    assert resp.status_code == 200
    assert resp.text == "authenticated"

    resp2 = client.get("/test?auth_token=secret-token-888")
    assert resp2.status_code == 200
    assert resp2.text == "authenticated"


def test_parse_args_auth_token():
    args = parse_args(["--auth-token", "my-secret-key-123"])
    assert args.auth_token == "my-secret-key-123"

    cfg = resolve_runtime_config(args=args, env={})
    assert cfg.auth_token == "my-secret-key-123"


def test_env_auth_token():
    env = {"MCP_RDBMS_AUTH_TOKEN": "env-token-xyz"}
    cfg = resolve_runtime_config(args=None, env=env)
    assert cfg.auth_token == "env-token-xyz"


def test_token_auth_options_preflight_bypass():
    """验证 OPTIONS 跨域预检请求自动免认证放行，不被 401 拦截."""
    app = Starlette(
        routes=[Route("/test", endpoint=_dummy_endpoint, methods=["GET", "OPTIONS"])]
    )
    app.add_middleware(TokenAuthMiddleware, token="secret-token-888")
    client = TestClient(app)

    resp = client.options("/test")
    assert resp.status_code == 200
    assert resp.text == "authenticated"



def test_health_and_ping_probes_unauthenticated():
    """验证 /health 与 /ping 探针免密放行且返回健康状态."""
    from atengk_mcp_server_rdbms.server import create_server

    server = create_server()
    app = server.sse_app()
    app.add_middleware(TokenAuthMiddleware, token="secret-token-888")
    client = TestClient(app)

    # 1. /health 探活
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "ok"
    assert resp_health.json()["service"] == "mcp-server-rdbms"

    # 2. /ping 心跳
    resp_ping = client.get("/ping")
    assert resp_ping.status_code == 200
    assert resp_ping.json()["status"] == "pong"


def test_cors_middleware_integration():
    """验证 CORS 中间件与令牌门禁集成，OPTIONS 返回 200，未授权 401 亦携带 CORS 头."""
    from starlette.middleware.cors import CORSMiddleware

    app = _create_app("secret-token-888")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    client = TestClient(app)

    # 1. 跨域 OPTIONS 预检
    resp_opt = client.options(
        "/test",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp_opt.status_code == 200
    assert resp_opt.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    # 2. 未授权跨域 GET，401 响应亦必须包含 CORS 头部
    resp_unauth = client.get("/test", headers={"Origin": "http://localhost:3000"})
    assert resp_unauth.status_code == 401
    assert resp_unauth.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_parse_args_and_env_edge_security():
    """验证 allowed-hosts, allowed-origins 与 cors-origins 参数和环境变量解析."""
    # CLI 解析
    args = parse_args([
        "--allowed-hosts", "mcp.example.com,192.168.1.*",
        "--allowed-origins", "http://localhost:3000,https://ai.example.com",
        "--cors-origins", "*",
    ])
    assert args.allowed_hosts == "mcp.example.com,192.168.1.*"
    assert args.allowed_origins == "http://localhost:3000,https://ai.example.com"
    assert args.cors_origins == "*"

    cfg = resolve_runtime_config(args=args, env={})
    assert cfg.allowed_hosts == ("mcp.example.com", "192.168.1.*")
    assert cfg.allowed_origins == ("http://localhost:3000", "https://ai.example.com")
    assert cfg.cors_origins == ("*",)

    # 环境变量解析
    env = {
        "MCP_RDBMS_ALLOWED_HOSTS": "api.domain.com",
        "MCP_RDBMS_ALLOWED_ORIGINS": "https://chat.domain.com",
        "MCP_RDBMS_CORS_ORIGINS": "https://chat.domain.com,https://admin.domain.com",
    }
    cfg2 = resolve_runtime_config(args=None, env=env)
    assert cfg2.allowed_hosts == ("api.domain.com",)
    assert cfg2.allowed_origins == ("https://chat.domain.com",)
    assert cfg2.cors_origins == ("https://chat.domain.com", "https://admin.domain.com")

