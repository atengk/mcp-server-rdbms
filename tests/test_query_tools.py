"""
mcp-server-rdbms: 只读查询与执行计划核心工具测试.

@author Ateng
@since 2026-10-04
"""

import time
from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.tools.sql_query import register_query_tools


@pytest.fixture
def query_setup():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    engine = registry.get_engine("default")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                score NUMERIC NOT NULL,
                avatar BLOB
            );
        """))
        # 插入包含大 BLOB (> 1KB) 与普通数据的记录
        large_blob = b"a" * 2048
        conn.execute(
            text("INSERT INTO users (id, username, score, avatar) VALUES (:id, :name, :score, :avatar)"),
            [
                {"id": 1, "name": "alice", "score": 95.5, "avatar": b"small_img"},
                {"id": 2, "name": "bob", "score": 80.0, "avatar": large_blob},
            ],
        )
        conn.commit()

    server = MCPServer(name="test-server")
    register_query_tools(server, registry)
    return server, registry


@pytest.mark.asyncio
async def test_sql_query_json_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {"sql": "SELECT id, username, score FROM users ORDER BY id"})
    data = result.structured_content

    assert data["format"] == "json"
    assert data["row_count"] == 2
    assert data["columns"] == ["id", "username", "score"]
    rows = data["data"]
    assert rows[0]["username"] == "alice"
    assert rows[0]["score"] == 95.5
    assert rows[1]["username"] == "bob"


@pytest.mark.asyncio
async def test_sql_query_markdown_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {
        "sql": "SELECT id, username FROM users ORDER BY id",
        "format": "markdown",
    })
    data = result.structured_content

    assert data["format"] == "markdown"
    assert "| id | username |" in data["data"]
    assert "| 1 | alice |" in data["data"]


@pytest.mark.asyncio
async def test_sql_query_csv_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {
        "sql": "SELECT id, username FROM users ORDER BY id",
        "format": "csv",
    })
    data = result.structured_content

    assert data["format"] == "csv"
    lines = data["data"].strip().splitlines()
    assert lines[0] == "id,username"
    assert lines[1] == "1,alice"
    assert lines[2] == "2,bob"


@pytest.mark.asyncio
async def test_sql_query_blob_truncation(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {"sql": "SELECT id, avatar FROM users WHERE id = 2"})
    data = result.structured_content

    rows = data["data"]
    assert "<BLOB 2048 bytes:" in rows[0]["avatar"]
    assert "[truncated]>" in rows[0]["avatar"]


@pytest.mark.asyncio
async def test_sql_query_security_violations(query_setup):
    server, _ = query_setup

    # 1. 尝试执行 DML
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "DELETE FROM users WHERE id = 1"})
    assert "只读" in str(exc_info.value)

    # 2. 尝试执行 DDL
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "DROP TABLE users"})
    assert "只读" in str(exc_info.value)

    # 3. 尝试多语句拼接注入
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "SELECT 1; SELECT 2;"})
    assert "多条" in str(exc_info.value) or "多语句" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_timeout_breaker(query_setup):
    server, _ = query_setup

    def slow_exec(*args, **kwargs):
        time.sleep(0.1)
        return [], []

    with patch("atengk_mcp_server_rdbms.tools.sql_query._execute_query_sync", side_effect=slow_exec):
        with pytest.raises(ToolError) as exc_info:
            await server.call_tool("sql_query", {"sql": "SELECT * FROM users", "timeout": 0.01})
        assert "超时" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_explain(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_explain", {"sql": "SELECT * FROM users WHERE id = 1"})
    data = result.structured_content

    assert "SELECT * FROM users WHERE id = 1" in data["query"]
    assert isinstance(data["plan"], list)
    assert len(data["plan"]) > 0


@pytest.mark.asyncio
async def test_sql_explain_security_violation(query_setup):
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_explain", {"sql": "DROP TABLE users"})
    assert "只读" in str(exc_info.value)
