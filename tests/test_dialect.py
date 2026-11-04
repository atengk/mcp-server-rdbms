"""
mcp-server-rdbms: 方言拦截器与驱动缺失诊断测试.

@author Ateng
@since 2026-10-04
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import NoSuchModuleError, OperationalError

from atengk_mcp_server_rdbms.core.dialect import DialectReadOnlyAdapter, DialectRegistry
from atengk_mcp_server_rdbms.core.exceptions import DriverMissingError


def test_oracle_missing_driver_hint():
    hint = DialectRegistry.get_install_hint("oracle+oracledb://scott:tiger@localhost/xe")
    assert "oracle" in hint
    assert "uv pip install" in hint
    assert 'atengk-mcp-server-rdbms[oracle]' in hint


def test_mssql_missing_driver_hint():
    hint = DialectRegistry.get_install_hint("mssql+pyodbc://localhost/test")
    assert "mssql" in hint
    assert "uv pip install" in hint
    assert 'atengk-mcp-server-rdbms[mssql]' in hint


def test_clickhouse_missing_driver_hint():
    hint = DialectRegistry.get_install_hint("clickhouse+connect://localhost:8123/default")
    assert "clickhouse" in hint
    assert "uv pip install" in hint
    assert 'atengk-mcp-server-rdbms[clickhouse]' in hint


def test_unknown_dialect_hint():
    hint = DialectRegistry.get_install_hint("custom_db://localhost:1234/db")
    assert "custom_db" in hint
    assert "uv pip install" in hint


def test_intercept_raises_driver_missing_error():
    exc = NoSuchModuleError("Can't load plugin: sqlalchemy.dialects:oracle")
    with pytest.raises(DriverMissingError) as exc_info:
        DialectRegistry.intercept("oracle+oracledb://localhost", exc)
    
    assert "oracle" in str(exc_info.value)
    assert "uv pip install" in str(exc_info.value)


def test_dialect_readonly_adapter_sqlite_blocks_writes():
    """验证 SQLite 连接在应用只读会话适配后，引擎底层物理拦截写操作."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        applied = DialectReadOnlyAdapter.apply_readonly(conn, "sqlite")
        assert applied is True

        # 验证只读查询正常
        res = conn.execute(text("SELECT 1 AS val")).fetchall()
        assert res[0][0] == 1

        # 验证写操作被 SQLite 引擎底层物理拦截
        with pytest.raises(OperationalError) as exc_info:
            conn.execute(text("CREATE TABLE hack (id INT)"))
        assert "readonly" in str(exc_info.value).lower()


def test_dialect_readonly_adapter_sql_mapping():
    """验证已知主流方言的只读 SQL 指令映射."""
    assert "PRAGMA query_only" in DialectReadOnlyAdapter.get_readonly_sql("sqlite")
    assert "TRANSACTION READ ONLY" in DialectReadOnlyAdapter.get_readonly_sql("postgresql")
    assert "TRANSACTION READ ONLY" in DialectReadOnlyAdapter.get_readonly_sql("postgres")
    assert "TRANSACTION READ ONLY" in DialectReadOnlyAdapter.get_readonly_sql("mysql")
    assert "TRANSACTION READ ONLY" in DialectReadOnlyAdapter.get_readonly_sql("tidb")
    assert "TRANSACTION READ ONLY" in DialectReadOnlyAdapter.get_readonly_sql("oracle")
    assert "readonly = 1" in DialectReadOnlyAdapter.get_readonly_sql("clickhouse")


def test_dialect_readonly_adapter_graceful_degradation(monkeypatch):
    """验证未知或不支持只读事务的方言在报错时优雅降级并记录警告."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = OperationalError("Syntax error", params=None, orig=Exception("bad"))

    applied = DialectReadOnlyAdapter.apply_readonly(mock_conn, "unsupported_db")
    assert applied is False

