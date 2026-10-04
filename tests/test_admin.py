"""
mcp-server-rdbms: 数据库活动进程与长查询运维观测测试.

@author Ateng
@since 2026-10-04
"""

from unittest.mock import MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.tools.admin_queries import register_admin_tools


@pytest.fixture
def admin_server():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")

    server = MCPServer(name="test-admin-server")
    register_admin_tools(server, registry)
    return server, registry


@pytest.mark.asyncio
async def test_admin_list_running_queries_sqlite_graceful_degrade(admin_server):
    """验证 SQLite 轻量内嵌库自适应优雅降级，返回空列表与友好说明，不抛异常."""
    server, _ = admin_server

    result = await server.call_tool("admin_list_running_queries", {})
    data = result.structured_content

    assert data["supported"] is False
    assert data["dialect"] == "sqlite"
    assert data["queries"] == []
    assert "不支持" in data["message"]


@pytest.mark.asyncio
async def test_admin_list_running_queries_not_found_db(admin_server):
    """验证指定不存在的数据库别名时抛出明确的 ToolError."""
    server, _ = admin_server

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("admin_list_running_queries", {"db": "non_existent"})

    assert "non_existent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_admin_list_running_queries_offloaded_to_threadpool(admin_server):
    """验证活动查询运维观测同步操作卸载到 AnyIO 线程池执行."""
    server, _ = admin_server

    with patch("anyio.to_thread.run_sync", wraps=__import__("anyio").to_thread.run_sync) as spy_run_sync:
        await server.call_tool("admin_list_running_queries", {})
        assert spy_run_sync.called


@pytest.mark.asyncio
async def test_admin_list_running_queries_mocked_postgresql(admin_server):
    """验证支持方言（如 PostgreSQL）正常返回活动查询列表."""
    server, registry = admin_server

    # Mock PostgreSQL 引擎与查询返回
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"

    mock_row = {
        "pid": 12345,
        "user": "postgres",
        "db": "analytics",
        "duration_seconds": 12.34,
        "state": "active",
        "query": "SELECT * FROM large_table",
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value = [mock_row]

    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.execute.return_value = mock_result
    mock_engine.connect.return_value = mock_conn

    with patch.object(registry, "get_engine", return_value=mock_engine):
        result = await server.call_tool("admin_list_running_queries", {})
        data = result.structured_content

        assert data["supported"] is True
        assert data["dialect"] == "postgresql"
        assert len(data["queries"]) == 1
        query_entry = data["queries"][0]
        assert query_entry["pid"] == 12345
        assert query_entry["user"] == "postgres"
        assert query_entry["duration_seconds"] == 12.34
        assert query_entry["query"] == "SELECT * FROM large_table"
