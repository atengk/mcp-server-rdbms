"""
mcp-server-rdbms: 连接注册表与引擎管理测试.

@author Ateng
@since 2026-10-04
"""

import pytest
from sqlalchemy import text

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
)
from atengk_mcp_server_rdbms.models.connection import ConnectionProfile


def test_empty_registry_list_profiles():
    registry = ConnectionRegistry()
    assert registry.list_profiles() == []


def test_register_and_get_sqlite_engine():
    registry = ConnectionRegistry()
    profile = registry.register_url("sqlite:///:memory:", name="test_mem")
    
    assert profile.name == "test_mem"
    assert profile.dialect == "sqlite"
    assert profile.is_default is True

    engine = registry.get_engine("test_mem")
    assert engine is not None
    assert engine.dialect.name == "sqlite"

    with engine.connect() as conn:
        val = conn.scalar(text("SELECT 1"))
        assert val == 1


def test_default_routing():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default_db", is_default=True)
    
    engine = registry.get_engine()
    assert engine is not None
    assert registry.get_profile().name == "default_db"


def test_not_found_connection():
    registry = ConnectionRegistry()
    with pytest.raises(ConnectionNotFoundError) as exc_info:
        registry.get_engine("non_existent")
    assert "non_existent" in str(exc_info.value)


def test_password_masking_in_profile():
    profile = ConnectionProfile(
        name="secure_pg",
        url="postgresql://admin:super_secret_password@localhost:5432/prod_db",
    )
    assert "super_secret_password" not in profile.masked_url
    assert "***" in profile.masked_url
    assert profile.dialect in ("postgresql", "postgres")


def test_missing_driver_raises_driver_missing_error():
    registry = ConnectionRegistry()
    registry.register_url("oracle+oracledb://scott:tiger@localhost:1521/xe", name="oracle_db")

    with pytest.raises(DriverMissingError) as exc_info:
        registry.get_engine("oracle_db")

    assert "oracle" in str(exc_info.value)
    assert "uv pip install" in str(exc_info.value)


def test_close_all_cleans_engines():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="mem")
    engine = registry.get_engine("mem")
    assert engine is not None

    registry.close_all()
    assert len(registry._engines) == 0


def test_connection_not_found_contains_available_profiles_and_hint():
    """测试未找到连接时，错误信息包含当前可用列表与 rdbms://connections 自愈指引."""
    from atengk_mcp_server_rdbms.core.exceptions import ConnectionNotFoundError

    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="dev")
    registry.register_url("sqlite:///:memory:", name="prod")

    with pytest.raises(ConnectionNotFoundError) as exc_info:
        registry.get_profile("non_existent")

    err = str(exc_info.value)
    assert "non_existent" in err
    assert "dev" in err and "prod" in err
    assert "rdbms://connections" in err
    assert "自愈指引" in err


def test_connection_registry_effective_masking(tmp_path):
    """测试 ConnectionRegistry 解析连接级与全局脱敏配置继承与合并."""
    registry = ConnectionRegistry(mask_enabled=True, mask_columns=("global_col",))

    # 1. 默认继承全局
    registry.register_url("sqlite:///:memory:", name="db1")
    enabled1, cols1 = registry.get_effective_masking("db1")
    assert enabled1 is True
    assert cols1 == ("global_col",)

    # 2. 连接级显式关闭脱敏
    p2 = registry.register_url("sqlite:///:memory:", name="db2", mask_enabled=False)
    assert p2.mask_enabled is False
    enabled2, cols2 = registry.get_effective_masking("db2")
    assert enabled2 is False
    assert cols2 == ("global_col",)

    # 3. 连接级追加 mask_columns 合并去重
    registry.register_url(
        "sqlite:///:memory:",
        name="db3",
        mask_enabled=True,
        mask_columns=("local_col", "global_col"),
    )
    enabled3, cols3 = registry.get_effective_masking("db3")
    assert enabled3 is True
    assert cols3 == ("global_col", "local_col")

    # 4. 从 YAML 文件加载包含 mask_enabled 与 mask_columns
    cfg_file = tmp_path / "test_conns.yaml"
    cfg_file.write_text("""
connections:
  prod:
    url: "sqlite:///:memory:"
    mask_enabled: true
    mask_columns: ["prod_secret", "id_card"]
  test_env:
    url: "sqlite:///:memory:"
    mask_enabled: false
""", encoding="utf-8")

    file_reg = ConnectionRegistry.from_file(cfg_file)
    p_prod = file_reg.get_profile("prod")
    assert p_prod.mask_enabled is True
    assert p_prod.mask_columns == ("prod_secret", "id_card")

    p_test = file_reg.get_profile("test_env")
    assert p_test.mask_enabled is False
    assert p_test.mask_columns == ()


