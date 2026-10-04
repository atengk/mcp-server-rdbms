"""
mcp-server-rdbms: 模式与系统表过滤器测试.

@author Ateng
@since 2026-10-04
"""

import pytest

from atengk_mcp_server_rdbms.core.schema_filter import SchemaFilter


@pytest.mark.parametrize(
    ("schema_name", "expected"),
    [
        ("information_schema", True),
        ("INFORMATION_SCHEMA", True),
        ("pg_catalog", True),
        ("PG_CATALOG", True),
        ("pg_toast", True),
        ("mysql", True),
        ("performance_schema", True),
        ("sys", True),
        ("public", False),
        ("main", False),
        ("app_schema", False),
        (None, False),
    ],
)
def test_is_system_schema(schema_name, expected):
    assert SchemaFilter.is_system_schema(schema_name) is expected


@pytest.mark.parametrize(
    ("table_name", "dialect", "expected"),
    [
        ("sqlite_sequence", "sqlite", True),
        ("sqlite_stat1", "sqlite", True),
        ("users", "sqlite", False),
        ("orders", "postgresql", False),
        ("sqlite_sequence", "postgresql", False),
    ],
)
def test_is_system_table(table_name, dialect, expected):
    assert SchemaFilter.is_system_table(table_name, dialect=dialect) is expected


def test_filter_tables():
    raw_tables = ["users", "sqlite_sequence", "orders", "sqlite_stat1"]
    filtered = SchemaFilter.filter_tables(raw_tables, dialect="sqlite")
    assert filtered == ["users", "orders"]
