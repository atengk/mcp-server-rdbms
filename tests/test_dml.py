"""
mcp-server-rdbms: DML 数据操作、写权限门禁与原子事务回滚测试.

@author Ateng
@since 2026-10-04
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text

from mcp_server_rdbms.core.audit import AuditLogger
from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.tools.sql_dml import register_dml_tools


@pytest.fixture
def dml_env(tmp_path: Path):
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    engine = registry.get_engine("default")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL
            );
        """))
        conn.execute(text("""
            INSERT INTO products (id, name, price) VALUES
            (1, 'apple', 5.0),
            (2, 'banana', 3.0);
        """))
        conn.commit()

    audit_file = tmp_path / "audit.log"
    audit = AuditLogger(log_file=str(audit_file))

    def make_server(allow_dml: bool = False):
        server = MCPServer(name="test-server")
        register_dml_tools(server, registry, allow_dml=allow_dml, audit=audit)
        return server

    return make_server, registry, audit_file


@pytest.mark.asyncio
async def test_sql_dml_disabled_by_default(dml_env):
    make_server, _, audit_file = dml_env
    server = make_server(allow_dml=False)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_dml", {"sql": "INSERT INTO products (id, name, price) VALUES (3, 'orange', 4.0)"})

    err_text = str(exc_info.value)
    assert "只读模式保护" in err_text
    assert "--allow-dml" in err_text

    # 验证未授权尝试亦记录审计
    assert audit_file.exists()
    logs = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(logs) >= 1
    last_log = json.loads(logs[-1])
    assert last_log["status"] == "FAILED"
    assert "duration_ms" in last_log
    assert last_log["duration_ms"] >= 0.0


@pytest.mark.asyncio
async def test_sql_dml_single_and_batch_success(dml_env):
    make_server, registry, audit_file = dml_env
    server = make_server(allow_dml=True)

    # 1. 单条 INSERT
    res1 = await server.call_tool("sql_dml", {"sql": "INSERT INTO products (id, name, price) VALUES (3, 'cherry', 8.0)"})
    data1 = res1.structured_content
    assert data1["success"] is True
    assert data1["statements_executed"] == 1
    assert data1["rows_affected"] == 1

    # 2. 批量 UPDATE 与 DELETE
    batch_sql = [
        "UPDATE products SET price = 5.5 WHERE id = 1",
        "DELETE FROM products WHERE id = 2",
    ]
    res2 = await server.call_tool("sql_dml", {"sql": batch_sql})
    data2 = res2.structured_content
    assert data2["success"] is True
    assert data2["statements_executed"] == 2

    # 验证数据库实际变更
    engine = registry.get_engine("default")
    with engine.connect() as conn:
        p1 = conn.execute(text("SELECT price FROM products WHERE id = 1")).scalar()
        assert p1 == 5.5
        p2 = conn.execute(text("SELECT COUNT(*) FROM products WHERE id = 2")).scalar()
        assert p2 == 0

    # 验证成功审计记录
    logs = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(logs) >= 2
    last_log = json.loads(logs[-1])
    assert last_log["status"] == "SUCCESS"
    assert last_log["rows_affected"] >= 0


@pytest.mark.asyncio
async def test_sql_dml_atomic_batch_rollback_on_failure(dml_env):
    make_server, registry, _ = dml_env
    server = make_server(allow_dml=True)

    # 构造包含主键冲突的批量 SQL：第一条原本会成功，第二条必失败
    failing_batch = [
        "INSERT INTO products (id, name, price) VALUES (10, 'watermelon', 20.0)",
        "INSERT INTO products (id, name, price) VALUES (10, 'duplicate_key', 99.0)",
    ]

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_dml", {"sql": failing_batch})

    assert "回滚" in str(exc_info.value)

    # 验证第一条操作是否全量回滚，未留脏数据
    engine = registry.get_engine("default")
    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM products WHERE id = 10")).scalar()
        assert cnt == 0


@pytest.mark.asyncio
async def test_sql_dml_no_where_blocked(dml_env):
    make_server, _, _ = dml_env
    server = make_server(allow_dml=True)

    # UPDATE 无 WHERE 条件被拦截
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_dml", {"sql": "UPDATE products SET price = 0"})
    assert "WHERE" in str(exc_info.value)

    # DELETE 无 WHERE 条件被拦截
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_dml", {"sql": "DELETE FROM products"})
    assert "WHERE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_dml_offloaded_to_threadpool(dml_env):
    make_server, _, _ = dml_env
    server = make_server(allow_dml=True)

    with patch("anyio.to_thread.run_sync", wraps=__import__("anyio").to_thread.run_sync) as spy_run_sync:
        await server.call_tool("sql_dml", {"sql": "UPDATE products SET price = 9.9 WHERE id = 1"})
        assert spy_run_sync.called


@pytest.mark.asyncio
async def test_sql_dml_semicolon_injection_blocked(dml_env):
    make_server, _, _ = dml_env
    server = make_server(allow_dml=True)

    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_dml",
            {"sql": "UPDATE products SET price = 1 WHERE id = 1; DELETE FROM products WHERE id = 2"},
        )
    assert "单条独立语句" in str(exc_info.value)
