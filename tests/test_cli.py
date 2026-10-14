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


def test_build_registry_from_env_var_ignored_without_prefix():
    """验证未带规范前缀的通用环境变量 DATABASE_URL 被严格忽略."""
    args = parse_args([])
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=True):
        registry = build_registry_from_args(args)
        assert len(registry.list_profiles()) == 0


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

    # 验证服务已挂载核心 6 工具
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    expected_tools = {
        "db_info",
        "schema_list_tables",
        "schema_describe_table",
        "sql_query",
        "sql_dml",
        "sql_ddl",
    }
    assert set(tool_names) == expected_tools
    assert len(tools) == 6

    # 验证直接调用工具
    result = await server.call_tool("db_info", {})
    assert result.structured_content["current_connection"]["dialect"] == "sqlite"


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


def test_parse_args_doctor_options():
    """验证 --doctor 与 --format 参数解析正确性."""
    args = parse_args(["--doctor", "--format", "json"])
    assert args.doctor is True
    assert args.format == "json"

    default_args = parse_args([])
    assert default_args.doctor is False
    assert default_args.format == "text"


def test_cli_subprocess_version_flag():
    """验证通过真实子进程执行 --version 与 -v 正常输出运行时环境信息."""
    for flag in ["--version", "-v"]:
        proc = subprocess.run(
            [sys.executable, "-m", "atengk_mcp_server_rdbms", flag],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert "atengk-mcp-server-rdbms v" in proc.stdout
        assert "Python" in proc.stdout
        assert "SQLAlchemy" in proc.stdout


def test_cli_subprocess_enhanced_help():
    """验证 --help 包含增强的使用示例、环境变量速查表与驱动安装指引."""
    proc = subprocess.run(
        [sys.executable, "-m", "atengk_mcp_server_rdbms", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "使用示例 (Examples)" in proc.stdout
    assert "专属环境变量速查表 (Dedicated Environment Variables)" in proc.stdout
    assert "可选驱动一键安装指引 (Dialect Drivers)" in proc.stdout
    assert "--doctor" in proc.stdout


def test_cli_subprocess_doctor_json():
    """验证通过子进程执行 --doctor --format json 输出结构化且合法的 JSON."""
    proc = subprocess.run(
        [sys.executable, "-m", "atengk_mcp_server_rdbms", "--doctor", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    import json
    data = json.loads(proc.stdout)
    assert "status" in data
    assert "drivers" in data
    assert "env_audit" in data
    assert "connections" in data


def test_cli_subprocess_doctor_text_with_db():
    """验证通过子进程传入 sqlite 内存库执行 --doctor 连通性成功并输出卡片."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "atengk_mcp_server_rdbms",
            "--db-url",
            "sqlite:///:memory:",
            "--doctor",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert "MCP Server RDBMS 运行环境与健康体检探针" in proc.stdout
    assert "关系型数据库驱动就绪矩阵" in proc.stdout
    assert "sqlite" in proc.stdout


def test_parse_args_server_metadata():
    """验证 --server-name 与 --server-instructions 参数解析正确性."""
    args = parse_args([
        "--server-name", "crm-db-service",
        "--server-instructions", "负责处理 CRM 数据库全量查询与管理操作",
    ])
    assert args.server_name == "crm-db-service"
    assert args.server_instructions == "负责处理 CRM 数据库全量查询与管理操作"


def test_build_server_with_custom_metadata():
    """验证 create_server 成功注入自定义名称与系统提示指令."""
    registry = ConnectionRegistry()
    server = create_server(
        registry,
        name="custom-db-server",
        instructions="专属业务指令说明",
    )
    assert server.name == "custom-db-server"
    assert server.instructions == "专属业务指令说明"


@pytest.mark.asyncio
async def test_tools_contain_multi_db_guidance():
    """验证 6 核心工具 description 均包含多库路由引导说明."""
    registry = ConnectionRegistry()
    server = create_server(registry)
    tools = await server.list_tools()
    tool_map = {t.name: t for t in tools}

    assert "多数据库" in tool_map["db_info"].description
    assert "多数据库路由" in tool_map["schema_list_tables"].description
    assert "多数据库路由" in tool_map["schema_describe_table"].description
    assert "多数据库路由" in tool_map["sql_query"].description
    assert "多数据库路由" in tool_map["sql_dml"].description
    assert "多数据库路由" in tool_map["sql_ddl"].description
