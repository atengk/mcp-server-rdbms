"""
mcp-server-rdbms: 分级审计流水、防爆截断与只读资源暴露专项测试套件.

@author Ateng
@since 2026-10-14
"""

import json
from pathlib import Path

import pytest
from mcp.server.mcpserver import MCPServer

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.env import resolve_runtime_config
from atengk_mcp_server_rdbms.resources.provider import register_resources
from atengk_mcp_server_rdbms.tools.sql_query import register_query_tools


def test_audit_modes_and_filtering(tmp_path: Path) -> None:
    """测试不同审计模式 (mutation, all, off) 下的过滤判断与落盘行为."""
    log_file = tmp_path / "test_audit.log"

    # 1. mutation 模式：仅写操作
    logger_mutation = AuditLogger(log_file=log_file, mode="mutation")
    assert logger_mutation.should_record("sql_dml") is True
    assert logger_mutation.should_record("sql_ddl") is True
    assert logger_mutation.should_record("sql_query") is False

    logger_mutation.record(operation="sql_query", statements=["SELECT 1"])
    assert not log_file.exists()  # 未写入

    logger_mutation.record(operation="sql_dml", statements=["UPDATE users SET status = 1 WHERE id = 1"])
    assert log_file.exists()
    events = logger_mutation.get_recent_events()
    assert len(events) == 1
    assert events[0]["operation"] == "sql_dml"

    # 2. off 模式：全关闭
    log_off = tmp_path / "test_off.log"
    logger_off = AuditLogger(log_file=log_off, mode="off")
    assert logger_off.should_record("sql_dml") is False
    assert logger_off.should_record("sql_ddl") is False
    assert logger_off.should_record("sql_query") is False
    logger_off.record(operation="sql_dml", statements=["DELETE FROM users WHERE id = 2"])
    assert not log_off.exists()

    # 3. all 模式：全量记录
    log_all = tmp_path / "test_all.log"
    logger_all = AuditLogger(log_file=log_all, mode="all")
    assert logger_all.should_record("sql_query") is True
    assert logger_all.should_record("sql_dml") is True
    logger_all.record(operation="sql_query", statements=["SELECT * FROM orders WHERE id = 10"])
    assert log_all.exists()
    all_events = logger_all.get_recent_events()
    assert len(all_events) == 1
    assert all_events[0]["operation"] == "sql_query"


def test_audit_truncation_guard(tmp_path: Path) -> None:
    """测试超长 SQL 语句与超量批量语句的防爆截断保护."""
    log_file = tmp_path / "truncation_audit.log"
    logger = AuditLogger(log_file=log_file, mode="all", max_stmt_chars=100, max_statements=3)

    # 1. 单条长语句截断验证
    long_sql = "SELECT " + ("a" * 200) + " FROM demo"
    sanitized = logger.sanitize_statements([long_sql])
    assert len(sanitized) == 1
    assert "...[TRUNCATED" in sanitized[0]

    # 2. 批量语句超量截断验证
    many_stmts = [f"INSERT INTO t VALUES ({i})" for i in range(10)]
    batch_sanitized = logger.sanitize_statements(many_stmts)
    assert len(batch_sanitized) == 4  # 3 条原语句 + 1 条截断标记
    assert "[TRUNCATED: 7 statements omitted, total: 10]" in batch_sanitized[-1]


def test_audit_get_recent_events_ordering_and_robustness(tmp_path: Path) -> None:
    """测试最近审计事件的倒序读取与脏数据容灾."""
    log_file = tmp_path / "ordering_audit.log"
    logger = AuditLogger(log_file=log_file, mode="all")

    # 初始文件不存在
    assert logger.get_recent_events() == []

    # 依次记录 3 条操作
    logger.record(operation="sql_dml", statements=["UPDATE 1"], status="SUCCESS")
    logger.record(operation="sql_ddl", statements=["CREATE TABLE t2"], status="SUCCESS")
    logger.record(operation="sql_query", statements=["SELECT 3"], status="SUCCESS")

    events = logger.get_recent_events(limit=2)
    assert len(events) == 2
    # 倒序：第一条应为最新的 sql_query，第二条为 sql_ddl
    assert events[0]["operation"] == "sql_query"
    assert events[1]["operation"] == "sql_ddl"

    # 注入脏行测试容灾
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("corrupted json line\n")

    logger.record(operation="sql_dml", statements=["UPDATE 4"])
    events_after_corrupted = logger.get_recent_events(limit=5)
    assert len(events_after_corrupted) == 4
    assert events_after_corrupted[0]["operation"] == "sql_dml"


@pytest.mark.asyncio
async def test_sql_query_audit_integration(tmp_path: Path) -> None:
    """测试 sql_query 工具在 audit_mode=all 下正常记录审计流水."""
    log_file = tmp_path / "query_audit.log"
    logger = AuditLogger(log_file=log_file, mode="all")

    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="test_db", is_default=True)

    server = MCPServer(name="test_audit_server")
    register_query_tools(server, registry, audit=logger)

    # 准备表结构
    engine = registry.get_engine("test_db")
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("CREATE TABLE users (id INT, name TEXT)"))
        conn.execute(text("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')"))

    # 执行查询
    result = await server.call_tool("sql_query", {"sql": "SELECT * FROM users", "db": "test_db"})
    assert result.structured_content["row_count"] == 2

    recent = await logger.get_recent_events_async(limit=5)
    assert len(recent) == 1
    event = recent[0]
    assert event["operation"] == "sql_query"
    assert event["db"] == "test_db"
    assert event["status"] == "SUCCESS"
    assert event["rows_affected"] == 2
    assert event["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_audit_resource_endpoint(tmp_path: Path) -> None:
    """测试 rdbms://audit/recent MCP 资源端点的读取与降级."""
    log_file = tmp_path / "resource_audit.log"
    logger = AuditLogger(log_file=log_file, mode="mutation")
    logger.record(
        operation="sql_dml",
        db="main_db",
        statements=["UPDATE t SET v=1 WHERE id=1"],
        status="SUCCESS",
        rows_affected=1,
    )

    registry = ConnectionRegistry()
    server = MCPServer(name="test_res_server")
    register_resources(server, registry, audit=logger)

    resources = await server.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    assert "rdbms://audit/recent" in resource_uris

    contents = await server.read_resource("rdbms://audit/recent")
    data = json.loads(contents[0].content)

    assert data["audit_mode"] == "mutation"
    assert data["total"] == 1
    assert data["events"][0]["operation"] == "sql_dml"


def test_audit_env_and_cli_resolution() -> None:
    """测试审计配置从环境变量与命令行参数的分层解析."""
    import argparse

    # 1. 默认值
    cfg_default = resolve_runtime_config(env={})
    assert cfg_default.audit_log_file == "rdbms_mcp_audit.log"
    assert cfg_default.audit_mode == "mutation"
    assert cfg_default.audit_max_bytes == 10 * 1024 * 1024
    assert cfg_default.audit_backup_count == 5

    # 2. 环境变量注入
    env = {
        "MCP_RDBMS_AUDIT_LOG_FILE": "/var/log/rdbms_custom.log",
        "MCP_RDBMS_AUDIT_MODE": "ALL",
        "MCP_RDBMS_AUDIT_MAX_BYTES": "20971520",
        "MCP_RDBMS_AUDIT_BACKUP_COUNT": "10",
    }
    cfg_env = resolve_runtime_config(env=env)
    assert cfg_env.audit_log_file == "/var/log/rdbms_custom.log"
    assert cfg_env.audit_mode == "all"
    assert cfg_env.audit_max_bytes == 20971520
    assert cfg_env.audit_backup_count == 10

    # 3. CLI 参数覆盖环境变量
    args = argparse.Namespace(
        audit_log="cli_override.log",
        audit_mode="off",
        audit_max_bytes=1024,
        audit_backup_count=2,
    )
    cfg_cli = resolve_runtime_config(args=args, env=env)
    assert cfg_cli.audit_log_file == "cli_override.log"
    assert cfg_cli.audit_mode == "off"
    assert cfg_cli.audit_max_bytes == 1024
    assert cfg_cli.audit_backup_count == 2
