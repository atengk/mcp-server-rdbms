"""
mcp-server-rdbms: 方言拦截器与驱动缺失诊断测试.

@author Ateng
@since 2026-10-04
"""

import pytest
from sqlalchemy.exc import NoSuchModuleError

from atengk_mcp_server_rdbms.core.dialect import DialectRegistry
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
