"""
mcp-server-rdbms: 安全序列化与多格式结果集格式化测试.

@author Ateng
@since 2026-10-04
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from atengk_mcp_server_rdbms.core.serializer import SafeSerializer


def test_serialize_decimal_datetime_uuid():
    data = {
        "dec_float": Decimal("123.45"),
        "dec_int": Decimal(100),
        "dt": datetime(2026, 10, 4, 8, 30, 0, tzinfo=UTC),
        "uid": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "normal_str": "hello",
        "normal_int": 42,
    }
    serialized = SafeSerializer.serialize_value(data)
    assert serialized["dec_float"] == 123.45
    assert serialized["dec_int"] == 100
    assert serialized["dt"] == "2026-10-04T08:30:00+00:00"
    assert serialized["uid"] == "12345678-1234-5678-1234-567812345678"
    assert serialized["normal_str"] == "hello"


def test_blob_truncation():
    # 小于等于 1KB 的二进制转十六进制
    small_blob = b"hello world"
    small_res = SafeSerializer.serialize_value(small_blob)
    assert small_res == small_blob.hex()

    # 大于 1KB 的二进制进行摘要截断并标记尺寸
    large_blob = b"x" * 2048
    large_res = SafeSerializer.serialize_value(large_blob)
    assert "<BLOB 2048 bytes:" in large_res
    assert "[truncated]>" in large_res


def test_format_json():
    rows = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
    res = SafeSerializer.format_rows(rows, format_type="json")
    assert isinstance(res, list)
    assert len(res) == 2
    assert res[0]["name"] == "alice"


def test_format_markdown():
    rows = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
    res = SafeSerializer.format_rows(rows, format_type="markdown")
    assert isinstance(res, str)
    assert "| id | name |" in res
    assert "| --- | --- |" in res
    assert "| 1 | alice |" in res
    assert "| 2 | bob |" in res


def test_format_csv():
    rows = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
    res = SafeSerializer.format_rows(rows, format_type="csv")
    assert isinstance(res, str)
    lines = res.strip().splitlines()
    assert lines[0] == "id,name"
    assert lines[1] == "1,alice"
    assert lines[2] == "2,bob"


def test_empty_rows_formats():
    assert SafeSerializer.format_rows([], format_type="json") == []
    assert SafeSerializer.format_rows([], format_type="markdown") == "(0 行数据)"
    assert SafeSerializer.format_rows([], format_type="csv") == ""
