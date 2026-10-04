"""
mcp-server-rdbms: 核心工具端到端调用测试.

@author Ateng
@since 2026-10-04
"""

from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.tools.db_info import register_db_info_tool


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
