"""
mcp-server-rdbms: 多库 YAML 配置中心、连接脱敏与健康预检自愈测试.

@author Ateng
@since 2026-10-04
"""

from pathlib import Path

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.server import create_server
from atengk_mcp_server_rdbms.tools.db_info import register_db_info_tool


def test_registry_from_yaml_dict_format(tmp_path: Path):
    """验证从 YAML 映射字典格式解析多库配置."""
    yaml_file = tmp_path / "connections.yaml"
    yaml_file.write_text(
        """
default: secondary
connections:
  primary:
    url: "sqlite:///:memory:"
    read_only: false
  secondary:
    url: "postgresql://admin:secret123@localhost:5432/analytics"
    read_only: true
        """,
        encoding="utf-8",
    )

    registry = ConnectionRegistry.from_file(yaml_file)
    assert registry.default_alias == "secondary"
    assert len(registry.list_profiles()) == 2

    p1 = registry.get_profile("primary")
    assert p1.name == "primary"
    assert p1.read_only is False

    p2 = registry.get_profile("secondary")
    assert p2.name == "secondary"
    assert p2.read_only is True
    assert "secret123" not in p2.masked_url
    assert "***" in p2.masked_url


def test_registry_from_yaml_list_format(tmp_path: Path):
    """验证从 YAML 列表格式解析多库配置."""
    yaml_file = tmp_path / "connections.yaml"
    yaml_file.write_text(
        """
connections:
  - name: main_db
    url: "sqlite:///:memory:"
    read_only: false
    is_default: true
  - name: replica_db
    url: "mysql://root:pass888@db.local:3306/prod"
    read_only: true
        """,
        encoding="utf-8",
    )

    registry = ConnectionRegistry.from_file(yaml_file)
    assert registry.default_alias == "main_db"
    assert len(registry.list_profiles()) == 2
    assert "***" in registry.get_profile("replica_db").masked_url


def test_registry_from_json_format(tmp_path: Path):
    """验证从 JSON 格式文件解析多库配置."""
    json_file = tmp_path / "connections.json"
    json_file.write_text(
        """
{
  "default": "db1",
  "connections": {
    "db1": { "url": "sqlite:///:memory:", "read_only": true }
  }
}
        """,
        encoding="utf-8",
    )

    registry = ConnectionRegistry.from_file(json_file)
    assert registry.default_alias == "db1"
    assert registry.get_profile("db1").read_only is True


def test_registry_from_file_not_found(tmp_path: Path):
    """验证配置文件不存在时抛出 FileNotFoundError."""
    non_existent = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        ConnectionRegistry.from_file(non_existent)


def test_registry_from_file_invalid_format(tmp_path: Path):
    """验证非字典格式配置文件抛出 TypeError."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("- item1\n- item2", encoding="utf-8")
    with pytest.raises(TypeError):
        ConnectionRegistry.from_file(bad_file)


@pytest.mark.asyncio
async def test_db_list_connections_tool_masking():
    """验证 db_list_connections 工具输出全部连接并强制密码脱敏."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="local_mem", is_default=True, read_only=False)
    registry.register_url(
        "postgresql://super_user:very_sensitive_password@10.0.0.1:5432/corp",
        name="remote_pg",
        is_default=False,
        read_only=True,
    )

    server = MCPServer(name="test-server")
    register_db_info_tool(server, registry)

    result = await server.call_tool("db_list_connections", {})
    raw = result.structured_content
    items = raw if isinstance(raw, list) else raw.get("result", raw)
    assert isinstance(items, list)
    assert len(items) == 2

    # 验证密码强脱敏与属性完整性
    local_info = next(item for item in items if item["name"] == "local_mem")
    assert local_info["is_default"] is True
    assert local_info["read_only"] is False

    pg_info = next(item for item in items if item["name"] == "remote_pg")
    assert pg_info["is_default"] is False
    assert pg_info["read_only"] is True
    assert "very_sensitive_password" not in pg_info["url"]
    assert "***" in pg_info["url"]


@pytest.mark.asyncio
async def test_multi_db_dynamic_routing(tmp_path: Path):
    """验证全量工具支持 db 参数多库动态定位与路由."""
    registry = ConnectionRegistry()
    # 建立两个独立的 SQLite 内存库
    registry.register_url("sqlite:///:memory:", name="db_a", is_default=True, read_only=False)
    registry.register_url("sqlite:///:memory:", name="db_b", is_default=False, read_only=False)

    eng_a = registry.get_engine("db_a")
    eng_b = registry.get_engine("db_b")

    with eng_a.connect() as conn:
        conn.execute(text("CREATE TABLE table_in_a (id INT)"))
        conn.commit()

    with eng_b.connect() as conn:
        conn.execute(text("CREATE TABLE table_in_b (id INT)"))
        conn.commit()

    server = create_server(registry, allow_dml=True, allow_ddl=True)

    # 1. 默认路由至 db_a
    res_default = await server.call_tool("schema_list_tables", {})
    tables_default = [t["name"] for t in res_default.structured_content["tables"]]
    assert "table_in_a" in tables_default
    assert "table_in_b" not in tables_default

    # 2. 显式路由至 db_b
    res_b = await server.call_tool("schema_list_tables", {"db": "db_b"})
    tables_b = [t["name"] for t in res_b.structured_content["tables"]]
    assert "table_in_b" in tables_b
    assert "table_in_a" not in tables_b

    # 3. 传入不存在的别名抛出清晰异常
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("schema_list_tables", {"db": "non_existent_alias"})
    assert "non_existent_alias" in str(exc_info.value)


@pytest.mark.asyncio
async def test_connection_level_read_only_protection():
    """验证单连接配置 read_only=True 时即使全局开启写权限仍受独立只读保护."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="prod_replica", is_default=True, read_only=True)

    server = create_server(registry, allow_dml=True, allow_ddl=True)

    # DML 尝试被连接只读策略拦截
    with pytest.raises(ToolError) as exc_dml:
        await server.call_tool("sql_dml", {"sql": "UPDATE users SET score = 100 WHERE id = 1"})
    assert "只读保护" in str(exc_dml.value)

    # DDL 尝试被连接只读策略拦截
    with pytest.raises(ToolError) as exc_ddl:
        await server.call_tool("sql_ddl", {"sql": "CREATE TABLE hack (id INT)", "confirm": True})
    assert "只读保护" in str(exc_ddl.value)


def test_connection_pool_pre_ping_healing(tmp_path: Path):
    """验证底层连接被外部异常断开后，pool_pre_ping 自动探测并透明自愈重连."""
    db_file = tmp_path / "healing.db"
    registry = ConnectionRegistry()
    # 使用文件型 SQLite 测试普通 QueuePool/默认连接池的断线自愈行为
    registry.register_url(f"sqlite:///{db_file}", name="healing_db")

    engine = registry.get_engine("healing_db")

    # 1. 正常借出连接执行查询
    with engine.connect() as conn:
        val = conn.execute(text("SELECT 100")).scalar()
        assert val == 100

    # 2. 模拟底层连接由于服务端超时或网络抖动非正常关闭
    # 从连接池借出一个连接并强制关闭底层 raw DBAPI connection
    pool_conn = engine.pool.connect()
    raw_dbapi_conn = pool_conn.dbapi_connection
    raw_dbapi_conn.close()
    pool_conn.close()

    # 3. 再次通过 engine.connect() 执行查询，pool_pre_ping 应捕获失效连接并自动创建新连接自愈
    with engine.connect() as conn:
        val = conn.execute(text("SELECT 200")).scalar()
        assert val == 200
