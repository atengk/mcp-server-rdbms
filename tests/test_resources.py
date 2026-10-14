"""
mcp-server-rdbms: MCP 只读资源挂载与读取端到端测试.

@author Ateng
@since 2026-10-14
"""

import json
from unittest.mock import patch

import anyio
import pytest
from sqlalchemy import text

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.server import create_server


@pytest.fixture
def resource_registry():
    """提供带有真实测试表和多库配置的测试注册中心."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default", is_default=True)
    registry.register_url("sqlite:///:memory:", name="sqlite_analytics", is_default=False, read_only=True)
    registry.register_url(
        "mysql+pymysql://admin:SuperSecretPass@127.0.0.1:3306/prod_db",
        name="mysql_remote",
        is_default=False,
        read_only=True,
    )

    # 在 default 内存库中初始化两张测试表
    engine = registry.get_engine("default")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL)"))

    return registry


@pytest.mark.asyncio
async def test_resources_metadata_registration(resource_registry):
    """验证服务启动后正确暴露静态资源与动态资源模板."""
    server = create_server(resource_registry)

    # 1. 验证静态资源挂载
    resources = await server.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    assert "rdbms://connections" in resource_uris

    conn_res = next(r for r in resources if str(r.uri) == "rdbms://connections")
    assert conn_res.name == "connections"
    assert conn_res.mime_type == "application/json"

    # 2. 验证动态资源模板挂载
    templates = await server.list_resource_templates()
    template_uris = {t.uri_template for t in templates}
    assert "rdbms://{db}/schema" in template_uris

    schema_tmpl = next(t for t in templates if t.uri_template == "rdbms://{db}/schema")
    assert schema_tmpl.mime_type == "application/json"


@pytest.mark.asyncio
async def test_read_connections_resource(resource_registry):
    """验证读取 rdbms://connections 资源并校验密码脱敏与结构."""
    server = create_server(resource_registry)

    contents = await server.read_resource("rdbms://connections")
    assert len(contents) == 1
    content_item = next(iter(contents))
    assert content_item.mime_type == "application/json"

    data = json.loads(content_item.content)
    assert data["default_connection"] == "default"
    assert data["total"] == 3

    connections = data["connections"]
    conn_map = {c["name"]: c for c in connections}

    # 校验默认库
    assert conn_map["default"]["is_default"] is True
    assert conn_map["default"]["dialect"] == "sqlite"

    # 校验敏感密码脱敏
    mysql_conn = conn_map["mysql_remote"]
    assert "SuperSecretPass" not in mysql_conn["url"]
    assert "***" in mysql_conn["url"]
    assert mysql_conn["read_only"] is True


@pytest.mark.asyncio
async def test_read_schema_resource_success(resource_registry):
    """验证读取指定数据库的表清单资源概要."""
    server = create_server(resource_registry)

    contents = await server.read_resource("rdbms://default/schema")
    assert len(contents) == 1
    content_item = next(iter(contents))
    assert content_item.mime_type == "application/json"

    data = json.loads(content_item.content)
    assert data["db"] == "default"
    assert data["status"] == "connected"
    assert data["total_tables"] == 2

    table_names = {t["name"] for t in data["tables"]}
    assert table_names == {"users", "orders"}


@pytest.mark.asyncio
async def test_read_schema_resource_fallback_on_nonexistent_db(resource_registry):
    """验证请求不存在的数据库连接别名时优雅降级为 error 状态，不崩溃."""
    server = create_server(resource_registry)

    contents = await server.read_resource("rdbms://nonexistent_alias/schema")
    assert len(contents) == 1
    content_item = next(iter(contents))
    assert content_item.mime_type == "application/json"

    data = json.loads(content_item.content)
    assert data["db"] == "nonexistent_alias"
    assert data["status"] == "error"
    assert "未找到指定的数据库连接配置" in data["error"]
    assert data["tables"] == []
    assert data["total_tables"] == 0


@pytest.mark.asyncio
async def test_read_schema_resource_offload_rule(resource_registry):
    """验证读取模式资源时严格遵循 Offload Rule，将同步 I/O 卸载至工作线程池."""
    server = create_server(resource_registry)

    with patch("anyio.to_thread.run_sync", wraps=anyio.to_thread.run_sync) as spy_run_sync:
        contents = await server.read_resource("rdbms://default/schema")
        assert len(contents) == 1
        assert spy_run_sync.called


@pytest.mark.asyncio
async def test_read_schema_resource_fallback_on_sqlalchemy_error(resource_registry):
    """验证当底层数据库连接异常或报错时优雅降级为 error 状态，不崩溃."""
    server = create_server(resource_registry)

    from sqlalchemy.exc import OperationalError

    with patch(
        "atengk_mcp_server_rdbms.resources.provider.fetch_tables_summary",
        side_effect=OperationalError("Connection refused", None, None),
    ):
        contents = await server.read_resource("rdbms://default/schema")
        assert len(contents) == 1
        content_item = next(iter(contents))
        data = json.loads(content_item.content)
        assert data["db"] == "default"
        assert data["status"] == "error"
        assert "数据库连接不可达或探查失败" in data["error"]
        assert data["tables"] == []

