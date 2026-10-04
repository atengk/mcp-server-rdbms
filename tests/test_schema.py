"""
mcp-server-rdbms: 数据库表清单与表结构一站式探查测试.

@author Ateng
@since 2026-10-04
"""

from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.tools.schema_info import register_schema_tools


@pytest.fixture
def schema_setup():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    engine = registry.get_engine("default")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT
            );
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """))
        conn.execute(text("CREATE INDEX idx_orders_user ON orders(user_id);"))
        conn.execute(text("""
            CREATE VIEW v_user_orders AS
            SELECT u.username, o.total
            FROM users u
            JOIN orders o ON u.id = o.user_id;
        """))
        conn.commit()

    server = MCPServer(name="test-server")
    register_schema_tools(server, registry)
    return server, registry


@pytest.mark.asyncio
async def test_schema_list_tables_basic(schema_setup):
    server, _ = schema_setup
    result = await server.call_tool("schema_list_tables", {})
    data = result.structured_content

    table_names = [t["name"] for t in data["tables"]]
    assert "users" in table_names
    assert "orders" in table_names
    # 验证系统内部表 sqlite_sequence 被自动过滤
    assert "sqlite_sequence" not in table_names
    # 默认不包含视图
    assert "v_user_orders" not in table_names

    # 验证外键拓扑关系
    fks = data["foreign_keys"]
    assert len(fks) >= 1
    fk = next(f for f in fks if f["constrained_table"] == "orders")
    assert fk["constrained_columns"] == ["user_id"]
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]


@pytest.mark.asyncio
async def test_schema_list_tables_include_views(schema_setup):
    server, _ = schema_setup
    result = await server.call_tool("schema_list_tables", {"include_views": True})
    data = result.structured_content

    names = [t["name"] for t in data["tables"]]
    assert "v_user_orders" in names
    view_item = next(t for t in data["tables"] if t["name"] == "v_user_orders")
    assert view_item["type"] == "view"


@pytest.mark.asyncio
async def test_schema_list_tables_system_schema_filtered(schema_setup):
    server, _ = schema_setup
    result = await server.call_tool("schema_list_tables", {"schema": "information_schema"})
    data = result.structured_content
    # 系统模式应被过滤，返回空表列表与空外键列表
    assert data["tables"] == []
    assert data["foreign_keys"] == []


@pytest.mark.asyncio
async def test_schema_describe_table_orders(schema_setup):
    server, _ = schema_setup
    result = await server.call_tool("schema_describe_table", {"table_name": "orders"})
    data = result.structured_content

    assert data["table_name"] == "orders"
    col_names = [c["name"] for c in data["columns"]]
    assert "id" in col_names
    assert "user_id" in col_names
    assert "total" in col_names

    # 主键断言
    assert "id" in data["primary_key"]

    # 外键约束断言
    assert len(data["foreign_keys"]) == 1
    fk = data["foreign_keys"][0]
    assert fk["constrained_columns"] == ["user_id"]
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]

    # 索引断言
    idx_names = [idx["name"] for idx in data["indexes"]]
    assert "idx_orders_user" in idx_names


@pytest.mark.asyncio
async def test_schema_describe_table_not_found(schema_setup):
    server, _ = schema_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("schema_describe_table", {"table_name": "non_existent"})

    assert "未找到数据表" in str(exc_info.value)
    assert "non_existent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_schema_tools_offloaded_to_threadpool(schema_setup):
    server, _ = schema_setup
    with patch("anyio.to_thread.run_sync", wraps=__import__("anyio").to_thread.run_sync) as spy_run_sync:
        await server.call_tool("schema_list_tables", {})
        assert spy_run_sync.called

    with patch("anyio.to_thread.run_sync", wraps=__import__("anyio").to_thread.run_sync) as spy_run_sync:
        await server.call_tool("schema_describe_table", {"table_name": "users"})
        assert spy_run_sync.called
