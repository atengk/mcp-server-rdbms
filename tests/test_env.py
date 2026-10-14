"""
mcp-server-rdbms: 环境变量分层解析与连接串自动拼装测试套件.

@author Ateng
@since 2026-10-04
"""

import os

from atengk_mcp_server_rdbms.core.env import (
    assemble_db_url_from_env,
    load_dotenv_if_exists,
    parse_bool_env,
    resolve_runtime_config,
)


def test_parse_bool_env():
    """测试宽容布尔值转换器."""
    # 肯定值测试
    assert parse_bool_env("1") is True
    assert parse_bool_env("true") is True
    assert parse_bool_env("TRUE") is True
    assert parse_bool_env(" True ") is True
    assert parse_bool_env("yes") is True
    assert parse_bool_env("YES") is True
    assert parse_bool_env("on") is True
    assert parse_bool_env("t") is True

    # 否定值与空值测试
    assert parse_bool_env("0") is False
    assert parse_bool_env("false") is False
    assert parse_bool_env("no") is False
    assert parse_bool_env("off") is False
    assert parse_bool_env("f") is False
    assert parse_bool_env("") is False
    assert parse_bool_env(None) is False
    assert parse_bool_env("random") is False


def test_assemble_db_url_prioritizes_full_url():
    """测试全量 MCP_RDBMS_DB_URL 变量优先级最高，且忽略通用 DATABASE_URL."""
    env = {
        "MCP_RDBMS_DB_URL": "mysql+pymysql://custom:pass@1.2.3.4:3306/db1",
        "DATABASE_URL": "postgresql://pg:pass@localhost/pgdb",  # 兼容变量已废除，应被忽略
    }
    assert assemble_db_url_from_env(env) == "mysql+pymysql://custom:pass@1.2.3.4:3306/db1"

    # 验证仅有 DATABASE_URL 时不会被读取
    assert assemble_db_url_from_env({"DATABASE_URL": "postgresql://pg:pass@localhost/pgdb"}) is None


def test_assemble_db_url_with_special_character_password():
    """测试特殊字符密码自动执行 safe URL 编码."""
    env = {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_USER": "root",
        "MCP_RDBMS_PASSWORD": "Admin@123#$/:?",
        "MCP_RDBMS_DB_HOST": "192.168.1.100",
        "MCP_RDBMS_DB_PORT": "3306",
        "MCP_RDBMS_DATABASE": "shop_db",
        "MCP_RDBMS_PARAMS": "charset=utf8mb4",
    }
    url = assemble_db_url_from_env(env)
    assert url is not None
    assert "Admin%40123%23%24%2F%3A%3F" in url or "Admin%40123%23" in url
    assert url.startswith("mysql+pymysql://root:")
    assert "@192.168.1.100:3306/shop_db?charset=utf8mb4" in url


def test_assemble_db_url_prevents_double_encoding():
    """测试已手动编码的密码防止二次编码为 %25."""
    env = {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_USER": "root",
        "MCP_RDBMS_PASSWORD": "Admin%40123%23",
        "MCP_RDBMS_DB_HOST": "localhost",
        "MCP_RDBMS_DATABASE": "test",
    }
    url = assemble_db_url_from_env(env)
    assert url is not None
    assert "Admin%40123%23" in url
    assert "Admin%2540123" not in url


def test_assemble_db_url_postgresql_defaults():
    """测试 PostgreSQL 方言与默认端口推断."""
    env = {
        "MCP_RDBMS_DIALECT": "postgres",
        "MCP_RDBMS_USER": "postgres",
        "MCP_RDBMS_PASSWORD": "secret_password",
        "MCP_RDBMS_DATABASE": "analytics",
    }
    url = assemble_db_url_from_env(env)
    assert url == "postgresql+psycopg://postgres:secret_password@127.0.0.1:5432/analytics"


def test_assemble_db_url_sqlite():
    """测试 SQLite 内存库与文件库拼装."""
    # 内存库
    env_mem = {"MCP_RDBMS_DIALECT": "sqlite"}
    assert assemble_db_url_from_env(env_mem) == "sqlite:///:memory:"

    # 文件库
    env_file = {
        "MCP_RDBMS_DIALECT": "sqlite",
        "MCP_RDBMS_DATABASE": "./local_data.db",
    }
    assert assemble_db_url_from_env(env_file) == "sqlite:///./local_data.db"


def test_assemble_db_url_empty_env():
    """测试无任何数据库相关配置时安全返回 None."""
    assert assemble_db_url_from_env({}) is None


def test_assemble_db_url_with_space_password():
    """测试密码包含空格时安全转为 %20 确保 SQLAlchemy 能够准确还原."""
    env = {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_USER": "root",
        "MCP_RDBMS_PASSWORD": "Admin 123#",
        "MCP_RDBMS_DB_HOST": "127.0.0.1",
        "MCP_RDBMS_DATABASE": "shop",
    }
    url = assemble_db_url_from_env(env)
    assert url is not None
    assert "Admin%20123%23" in url


def test_assemble_db_url_host_isolation():
    """测试服务监听主机 MCP_RDBMS_SERVER_HOST 与数据库主机隔离，不发生互相污染."""
    env = {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_USER": "root",
        "MCP_RDBMS_PASSWORD": "pass",
        "MCP_RDBMS_SERVER_HOST": "0.0.0.0",  # 服务监听地址
        "MCP_RDBMS_DATABASE": "shop",
    }
    url = assemble_db_url_from_env(env)
    assert url is not None
    # 数据库主机应保持默认 127.0.0.1，而不是被服务监听的 0.0.0.0 污染
    assert "@127.0.0.1:3306" in url


def test_assemble_db_url_only_password_without_user():
    """测试仅有密码无用户名时的 URL 拼装格式."""
    env = {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_PASSWORD": "secret_pass",
        "MCP_RDBMS_DATABASE": "shop",
    }
    url = assemble_db_url_from_env(env)
    assert url is not None
    assert "mysql+pymysql://:secret_pass@127.0.0.1:3306/shop" == url


def test_resolve_runtime_config_hierarchy():
    """测试运行时配置分层回退与覆盖."""
    import argparse

    # 1. 命令行参数优先于环境变量
    env = {
        "MCP_RDBMS_TRANSPORT": "sse",
        "MCP_RDBMS_SERVER_HOST": "0.0.0.0",
        "MCP_RDBMS_SERVER_PORT": "9000",
        "MCP_RDBMS_ALLOW_DML": "false",
        "MCP_RDBMS_ALLOW_DDL": "false",
    }
    args = argparse.Namespace(
        config=None,
        db_url=None,
        transport="stdio",
        host="127.0.0.1",
        port=8080,
        allow_dml=True,
        allow_ddl=False,
    )
    cfg = resolve_runtime_config(
        args=args,
        env=env,
    )
    assert cfg.transport == "stdio"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8080
    assert cfg.allow_dml is True
    assert cfg.allow_ddl is False

    # 2. 无命令行参数时回退读取环境变量
    cfg_env = resolve_runtime_config(args=None, env=env)
    assert cfg_env.transport == "sse"
    assert cfg_env.host == "0.0.0.0"
    assert cfg_env.port == 9000
    assert cfg_env.allow_dml is False

    # 3. 环境变量不存在时回退到默认标准值
    cfg_default = resolve_runtime_config(args=None, env={})
    assert cfg_default.transport == "stdio"
    assert cfg_default.host == "127.0.0.1"
    assert cfg_default.port == 8000
    assert cfg_default.allow_dml is False
    assert cfg_default.allow_ddl is False


def test_strict_namespace_ignores_unprefixed_env():
    """测试系统通用无前缀环境变量被 100% 物理隔离忽略，杜绝串库与配置污染."""
    unprefixed_env = {
        "DATABASE_URL": "postgresql://hacker:pass@evil.com/leak",
        "HOST": "10.0.0.99",
        "PORT": "9999",
        "DB_HOST": "10.0.0.88",
        "DB_USER": "root",
        "DB_PASSWORD": "password",
        "CONFIG_FILE": "/etc/shadow",
        "DEFAULT_DB": "evil_db",
        "MCP_ALLOW_DML": "true",
        "MCP_ALLOW_DDL": "true",
        "MCP_TRANSPORT": "sse",
    }
    # 验证 URL 拼装不读取任何无前缀变量
    assert assemble_db_url_from_env(unprefixed_env) is None

    # 验证运行时配置不读取任何无前缀变量
    cfg = resolve_runtime_config(args=None, env=unprefixed_env)
    assert cfg.config_file is None
    assert cfg.db_url is None
    assert cfg.transport == "stdio"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8000
    assert cfg.allow_dml is False
    assert cfg.allow_ddl is False
    assert cfg.default_db is None



def test_load_dotenv_if_exists(tmp_path):
    """测试自适应加载本地 .env 文件且不覆盖既有环境变量."""
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "# 注释行\n"
        "TEST_NEW_KEY=hello_mcp\n"
        "TEST_QUOTED_KEY=\"with spaces\"\n"
        "TEST_EXISTING_KEY=from_file\n",
        encoding="utf-8",
    )

    # 预设已有环境变量
    os.environ["TEST_EXISTING_KEY"] = "from_system"

    try:
        loaded = load_dotenv_if_exists(str(dotenv_file))
        assert loaded.get("TEST_NEW_KEY") == "hello_mcp"
        assert loaded.get("TEST_QUOTED_KEY") == "with spaces"
        # 验证系统既有环境变量未被覆盖
        assert os.environ.get("TEST_EXISTING_KEY") == "from_system"
        assert "TEST_EXISTING_KEY" not in loaded
    finally:
        os.environ.pop("TEST_NEW_KEY", None)
        os.environ.pop("TEST_QUOTED_KEY", None)
        os.environ.pop("TEST_EXISTING_KEY", None)


def test_extract_multi_db_urls_from_env():
    """测试从环境变量提取多数据库连接与默认库配置."""
    from atengk_mcp_server_rdbms.core.env import extract_multi_db_urls_from_env

    env = {
        "MCP_RDBMS_DB_DEV": "mysql+pymysql://root:pass@localhost:3306/dev_db",
        "MCP_RDBMS_DB_PROD": "postgresql+psycopg://postgres:pass@remote:5432/prod_db",
        "MCP_RDBMS_DEFAULT_DB": "prod",
        "MCP_RDBMS_DB_HOST": "127.0.0.1",  # 保留关键字，不应被当作别名
        "MCP_RDBMS_DB_PORT": "3306",       # 保留关键字
    }
    conns, default_alias = extract_multi_db_urls_from_env(env)
    assert len(conns) == 2
    assert conns["dev"] == "mysql+pymysql://root:pass@localhost:3306/dev_db"
    assert conns["prod"] == "postgresql+psycopg://postgres:pass@remote:5432/prod_db"
    assert default_alias == "prod"


def test_build_registry_with_multi_db_env():
    """测试 build_registry 通过环境变量多库与默认库正确装配连接注册表."""
    from atengk_mcp_server_rdbms.cli import build_registry

    env = {
        "MCP_RDBMS_DB_PRIMARY": "sqlite:///:memory:",
        "MCP_RDBMS_DB_ANALYTICS": "sqlite:///:memory:",
        "MCP_RDBMS_DEFAULT_DB": "analytics",
    }
    cfg = resolve_runtime_config(args=None, env=env)
    assert cfg.default_db == "analytics"
    assert len(cfg.multi_db_urls) == 2

    registry = build_registry(cfg)
    assert registry.default_alias == "analytics"
    profiles = {p.name: p for p in registry.list_profiles()}
    assert "primary" in profiles
    assert "analytics" in profiles
    assert profiles["analytics"].is_default is True
    assert profiles["primary"].is_default is False

