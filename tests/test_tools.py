"""
mcp-server-rdbms: 核心工具端到端调用测试.

@author Ateng
@since 2026-10-04
"""

from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.tools.db_info import register_db_info_tool


@pytest.fixture
def test_setup():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    server = MCPServer(name="test-server")
    register_db_info_tool(server, registry)
    return server, registry


@pytest.mark.asyncio
async def test_db_get_info_sqlite_memory(test_setup):
    server, _ = test_setup
    result = await server.call_tool("db_get_info", {})
    data = result.structured_content

    assert data["dialect"] == "sqlite"
    assert data["driver"] == "pysqlite"
    assert data["current_schema"] == "main"
    assert data["current_user"] == "sqlite"
    assert data["database"] == ":memory:"
    assert data["connection"] == "default"
    assert data["server_version"] != ""


@pytest.mark.asyncio
async def test_db_get_info_offloaded_to_threadpool(test_setup):
    server, _ = test_setup
    with patch("anyio.to_thread.run_sync", wraps=__import__("anyio").to_thread.run_sync) as spy_run_sync:
        result = await server.call_tool("db_get_info", {})
        assert spy_run_sync.called
        assert result.structured_content["dialect"] == "sqlite"


@pytest.mark.asyncio
async def test_db_get_info_missing_driver():
    registry = ConnectionRegistry()
    registry.register_url("oracle+oracledb://scott:tiger@localhost:1521/xe", name="oracle_db")
    server = MCPServer(name="test-server")
    register_db_info_tool(server, registry)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("db_get_info", {"db": "oracle_db"})

    error_text = str(exc_info.value)
    assert "缺少数据库驱动支持" in error_text
    assert "uv pip install" in error_text


@pytest.mark.asyncio
async def test_db_get_info_connection_not_found():
    registry = ConnectionRegistry()
    server = MCPServer(name="test-server")
    register_db_info_tool(server, registry)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("db_get_info", {"db": "not_exists"})

    assert "未找到指定的数据库连接配置" in str(exc_info.value)


@pytest.mark.asyncio
async def test_db_info_default_success(test_setup):
    server, registry = test_setup
    registry.register_url(
        "postgresql://user:secret_pass@localhost:5432/test_db",
        name="db2",
        is_default=False,
    )

    result = await server.call_tool("db_info", {})
    data = result.structured_content

    # 1. 验证 connections 清单及密码强制脱敏
    assert "connections" in data
    assert len(data["connections"]) == 2
    default_conn = next(c for c in data["connections"] if c["name"] == "default")
    assert default_conn["is_default"] is True
    assert default_conn["dialect"] == "sqlite"

    db2_conn = next(c for c in data["connections"] if c["name"] == "db2")
    assert db2_conn["is_default"] is False
    assert "secret_pass" not in db2_conn["url"]
    assert "***" in db2_conn["url"]

    # 2. 验证 current_connection 活跃连接探查
    curr = data["current_connection"]
    assert curr is not None
    assert curr["connection"] == "default"
    assert curr["dialect"] == "sqlite"
    assert curr["current_schema"] == "main"
    assert curr["status"] == "connected"


@pytest.mark.asyncio
async def test_db_info_specified_db_success(test_setup):
    server, _ = test_setup
    result = await server.call_tool("db_info", {"db": "default"})
    data = result.structured_content

    assert data["connection"] == "default"
    assert data["dialect"] == "sqlite"
    assert data["status"] == "connected"
    assert data["database"] == ":memory:"


@pytest.mark.asyncio
async def test_db_info_specified_db_not_found(test_setup):
    server, _ = test_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("db_info", {"db": "non_existent"})
    assert "未找到指定的数据库连接配置" in str(exc_info.value)


@pytest.mark.asyncio
async def test_db_info_specified_db_missing_driver():
    registry = ConnectionRegistry()
    registry.register_url("oracle+oracledb://scott:tiger@localhost:1521/xe", name="oracle_db")
    server = MCPServer(name="test-server")
    register_db_info_tool(server, registry)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("db_info", {"db": "oracle_db"})
    assert "缺少数据库驱动支持" in str(exc_info.value)


@pytest.mark.asyncio
async def test_db_info_default_graceful_degradation():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="broken_db")
    server = MCPServer(name="test-server")
    register_db_info_tool(server, registry)

    # 模拟默认连接发生网络不可达或连接异常
    from sqlalchemy.exc import OperationalError

    with patch(
        "atengk_mcp_server_rdbms.tools.db_info.fetch_database_info",
        side_effect=OperationalError("Connection refused", params=None, orig=Exception("refused")),
    ):
        result = await server.call_tool("db_info", {})
        data = result.structured_content

        # 验证连接清单正常返回，未被阻断
        assert "connections" in data
        assert len(data["connections"]) == 1
        assert data["connections"][0]["name"] == "broken_db"

        # 验证 current_connection 降级为 error 状态并记录原因
        curr = data["current_connection"]
        assert curr["connection"] == "broken_db"
        assert curr["status"] == "error"
        assert "Connection refused" in curr["error"]

