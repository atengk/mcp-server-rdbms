"""
mcp-server-rdbms: 命令行参数解析与服务装配测试.

@author Ateng
@since 2026-10-04
"""

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from atengk_mcp_server_rdbms.cli import build_registry_from_args, parse_args
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.server import create_server


def test_parse_args_defaults():
    args = parse_args([])
    assert args.db_url is None
    assert args.config is None
    assert args.transport is None
    assert args.host is None
    assert args.port is None
    assert args.allow_dml is False
    assert args.allow_ddl is False


def test_parse_args_custom():
    args = parse_args([
        "--db-url", "sqlite:///:memory:",
        "--allow-dml",
        "--allow-ddl",
        "--transport", "sse",
        "--port", "9000",
    ])
    assert args.db_url == "sqlite:///:memory:"
    assert args.allow_dml is True
    assert args.allow_ddl is True
    assert args.transport == "sse"
    assert args.port == 9000


def test_build_registry_from_db_url():
    args = parse_args(["--db-url", "sqlite:///:memory:"])
    registry = build_registry_from_args(args)
    assert len(registry.list_profiles()) == 1
    profile = registry.get_profile()
    assert profile.url == "sqlite:///:memory:"
    assert profile.name == "default"


def test_build_registry_from_env_var():
    args = parse_args([])
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}):
        registry = build_registry_from_args(args)
        assert len(registry.list_profiles()) == 1
        assert registry.get_profile().url == "sqlite:///:memory:"


def test_build_registry_from_mcp_rdbms_db_url():
    args = parse_args([])
    with patch.dict(os.environ, {"MCP_RDBMS_DB_URL": "sqlite:///:memory:"}):
        registry = build_registry_from_args(args)
        assert len(registry.list_profiles()) == 1
        assert registry.get_profile().url == "sqlite:///:memory:"


def test_build_registry_from_atomic_env_vars():
    """测试通过原子环境变量拼装并自动完成特殊字符密码转义."""
    args = parse_args([])
    env = {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_USER": "root",
        "MCP_RDBMS_PASSWORD": "Admin@123#",
        "MCP_RDBMS_DB_HOST": "127.0.0.1",
        "MCP_RDBMS_DB_PORT": "3306",
        "MCP_RDBMS_DATABASE": "test_db",
    }
    with patch.dict(os.environ, env):
        registry = build_registry_from_args(args)
        assert len(registry.list_profiles()) == 1
        profile = registry.get_profile()
        assert profile.url == "mysql+pymysql://root:Admin%40123%23@127.0.0.1:3306/test_db"


def test_build_registry_from_mcp_config_env_var(tmp_path):
    config_file = tmp_path / "test_conns.yaml"
    config_file.write_text("connections:\n  demo:\n    url: 'sqlite:///:memory:'\n", encoding="utf-8")
    args = parse_args([])
    with patch.dict(os.environ, {"MCP_RDBMS_CONFIG": str(config_file)}):
        registry = build_registry_from_args(args)
        assert "demo" in [p.name for p in registry.list_profiles()]


@pytest.mark.asyncio
async def test_create_server_end_to_end():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    server = create_server(registry)

    # 验证服务已挂载核心工具
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "db_get_info" in tool_names
    assert "schema_list_tables" in tool_names
    assert "schema_describe_table" in tool_names
    assert "sql_query" in tool_names
    assert "sql_explain" in tool_names
    assert "sql_dml" in tool_names
    assert "sql_ddl" in tool_names
    assert "admin_list_running_queries" in tool_names

    # 验证直接调用工具
    result = await server.call_tool("db_get_info", {})
    assert result.structured_content["dialect"] == "sqlite"


def test_cli_subprocess_help_flag():
    """验证通过真实子进程 python -m atengk_mcp_server_rdbms --help 可正常执行."""
    proc = subprocess.run(
        [sys.executable, "-m", "atengk_mcp_server_rdbms", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--db-url" in proc.stdout


def test_cli_subprocess_missing_driver_exit():
    """验证通过真实子进程传入缺失驱动连接串时优雅拦截并退出码 1."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "atengk_mcp_server_rdbms", "--db-url", "oracle+oracledb://scott:tiger@localhost:1521/xe"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert proc.returncode == 1
    assert "缺少数据库驱动支持" in proc.stderr
    assert "uv pip install" in proc.stderr
