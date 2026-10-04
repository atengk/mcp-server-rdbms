"""
mcp-server-rdbms: 表结构定义变更 (DDL) 权限门禁与生命周期测试.

@author Ateng
@since 2026-10-04
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import inspect, text

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.tools.sql_ddl import register_ddl_tools


@pytest.fixture
def ddl_env(tmp_path: Path):
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")

    audit_file = tmp_path / "ddl_audit.log"
    audit = AuditLogger(log_file=str(audit_file))

    def make_server(allow_ddl: bool = False):
        server = MCPServer(name="test-ddl-server")
        register_ddl_tools(server, registry, allow_ddl=allow_ddl, audit=audit)
        return server

    return make_server, registry, audit_file


@pytest.mark.asyncio
async def test_sql_ddl_disabled_by_default(ddl_env):
    """验证未传 --allow-ddl 时拦截建表操作并记录审计流水."""
    make_server, _, audit_file = ddl_env
    server = make_server(allow_ddl=False)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_ddl",
            {"sql": "CREATE TABLE articles (id INT PRIMARY KEY)", "confirm": True},
        )

    err_text = str(exc_info.value)
    assert "只读模式保护" in err_text
    assert "--allow-ddl" in err_text

    # 验证审计流水记录
    assert audit_file.exists()
    logs = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(logs) >= 1
    last_log = json.loads(logs[-1])
    assert last_log["operation"] == "sql_ddl"
    assert last_log["status"] == "FAILED"
    assert "只读模式保护" in last_log["error"]


@pytest.mark.asyncio
async def test_sql_ddl_confirm_protection(ddl_env):
    """验证即使开启 --allow-ddl，未传 confirm=True 仍被二次确认防御拦截."""
    make_server, _, audit_file = ddl_env
    server = make_server(allow_ddl=True)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_ddl",
            {"sql": "CREATE TABLE articles (id INT PRIMARY KEY)", "confirm": False},
        )

    err_text = str(exc_info.value)
    assert "二次确认保护" in err_text
    assert "confirm=True" in err_text

    logs = audit_file.read_text(encoding="utf-8").strip().splitlines()
    last_log = json.loads(logs[-1])
    assert last_log["status"] == "FAILED"
    assert "二次确认保护" in last_log["error"]


@pytest.mark.asyncio
async def test_sql_ddl_create_alter_drop_lifecycle(ddl_env):
    """验证建表、改表与删表全生命周期执行及数据库结构真实变更."""
    make_server, registry, audit_file = ddl_env
    server = make_server(allow_ddl=True)
    engine = registry.get_engine("default")

    # 1. CREATE TABLE
    res1 = await server.call_tool(
        "sql_ddl",
        {
            "sql": "CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT NOT NULL)",
            "confirm": True,
        },
    )
    data1 = res1.structured_content
    assert data1["success"] is True
    assert "CREATE TABLE" in data1["statement"]

    inspector = inspect(engine)
    assert "items" in inspector.get_table_names()

    # 2. ALTER TABLE
    res2 = await server.call_tool(
        "sql_ddl",
        {
            "sql": "ALTER TABLE items ADD COLUMN price REAL",
            "confirm": True,
        },
    )
    assert res2.structured_content["success"] is True

    # 验证新列已在表中生效
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO items (id, title, price) VALUES (1, 'book', 29.9)"))
        conn.commit()
        row = conn.execute(text("SELECT price FROM items WHERE id = 1")).fetchone()
        assert row[0] == 29.9

    # 3. DROP TABLE
    res3 = await server.call_tool(
        "sql_ddl",
        {
            "sql": "DROP TABLE items",
            "confirm": True,
        },
    )
    assert res3.structured_content["success"] is True
    inspector = inspect(engine)
    assert "items" not in inspector.get_table_names()

    # 验证全部操作审计记录
    logs = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(logs) == 3
    for log_line in logs:
        entry = json.loads(log_line)
        assert entry["status"] == "SUCCESS"
        assert entry["operation"] == "sql_ddl"


@pytest.mark.asyncio
async def test_sql_ddl_non_ddl_and_multi_statement_blocked(ddl_env):
    """验证传入非 DDL 语句或多语句拼接被拦截并记录失败审计."""
    make_server, _, audit_file = ddl_env
    server = make_server(allow_ddl=True)

    # 非 DDL 语句（如 SELECT）
    with pytest.raises(ToolError) as exc_info1:
        await server.call_tool(
            "sql_ddl",
            {"sql": "SELECT 1", "confirm": True},
        )
    assert "仅允许执行结构定义变更" in str(exc_info1.value)

    # 多语句拼接
    with pytest.raises(ToolError) as exc_info2:
        await server.call_tool(
            "sql_ddl",
            {"sql": "CREATE TABLE t1 (id INT); CREATE TABLE t2 (id INT)", "confirm": True},
        )
    assert "严禁拼接执行多条" in str(exc_info2.value)

    logs = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(logs) == 2
    for log_line in logs:
        assert json.loads(log_line)["status"] == "FAILED"


@pytest.mark.asyncio
async def test_sql_ddl_offloaded_to_threadpool(ddl_env):
    """验证 DDL 执行卸载到 AnyIO 线程池."""
    make_server, _, _ = ddl_env
    server = make_server(allow_ddl=True)

    with patch("anyio.to_thread.run_sync", wraps=__import__("anyio").to_thread.run_sync) as spy_run_sync:
        await server.call_tool(
            "sql_ddl",
            {"sql": "CREATE TABLE test_pool (id INT)", "confirm": True},
        )
        assert spy_run_sync.called
