"""
mcp-server-rdbms: 连接注册表与引擎管理测试.

@author Ateng
@since 2026-10-04
"""

import pytest
from sqlalchemy import text

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.core.exceptions import ConnectionNotFoundError, DriverMissingError
from mcp_server_rdbms.models.connection import ConnectionProfile


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
