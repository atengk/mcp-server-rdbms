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


def test_text_truncation_boundary():
    # 刚好等于 2048 字符不截断
    exact_text = "a" * 2048
    assert SafeSerializer.serialize_value(exact_text) == exact_text

    # 超过 2048 字符自适应截断并追加长度标注
    long_text = "b" * 3000
    res = SafeSerializer.serialize_value(long_text)
    assert len(res) > 2048
    assert res.startswith("b" * 2048)
    assert res.endswith("... [已截断，总长度 3000 字符]")


def test_text_truncation_in_containers():
    data = {
        "short": "normal text",
        "long": "c" * 2500,
        "nested": ["item1", "d" * 2100],
    }
    res = SafeSerializer.serialize_value(data)
    assert res["short"] == "normal text"
    assert res["long"].endswith("... [已截断，总长度 2500 字符]")
    assert res["nested"][0] == "item1"
    assert res["nested"][1].endswith("... [已截断，总长度 2100 字符]")


def test_text_truncation_across_formats():
    long_text = "e" * 2500
    rows = [{"id": 1, "content": long_text}]

    # 1. JSON 格式
    json_res = SafeSerializer.format_rows(rows, format_type="json")
    assert isinstance(json_res, list)
    assert json_res[0]["content"].endswith("... [已截断，总长度 2500 字符]")

    # 2. Markdown 格式
    md_res = SafeSerializer.format_rows(rows, format_type="markdown")
    assert isinstance(md_res, str)
    assert "... [已截断，总长度 2500 字符]" in md_res

    # 3. CSV 格式
    csv_res = SafeSerializer.format_rows(rows, format_type="csv")
    assert isinstance(csv_res, str)
    assert "... [已截断，总长度 2500 字符]" in csv_res


def test_text_truncation_custom_length_and_disable(monkeypatch):
    """测试通过显式参数与环境变量自定义截断长度或关闭截断."""
    long_text = "x" * 3000

    # 1. 显式传入自定义截断阈值 100
    res_100 = SafeSerializer.serialize_value(long_text, max_text_length=100)
    assert res_100.startswith("x" * 100)
    assert res_100.endswith("... [已截断，总长度 3000 字符]")

    # 2. 显式传入 0 关闭截断（全量输出）
    res_unlimited = SafeSerializer.serialize_value(long_text, max_text_length=0)
    assert res_unlimited == long_text

    # 3. 显式传入负数关闭截断
    res_neg = SafeSerializer.serialize_value(long_text, max_text_length=-1)
    assert res_neg == long_text

    # 4. format_rows 支持 max_text_length=0 关闭截断
    rows = [{"content": long_text}]
    json_unlimited = SafeSerializer.format_rows(rows, format_type="json", max_text_length=0)
    assert json_unlimited[0]["content"] == long_text

    # 5. 环境变量 MCP_RDBMS_MAX_TEXT_LENGTH 动态控制
    monkeypatch.setenv("MCP_RDBMS_MAX_TEXT_LENGTH", "50")
    res_env = SafeSerializer.serialize_value(long_text)
    assert res_env.startswith("x" * 50)
    assert res_env.endswith("... [已截断，总长度 3000 字符]")

    # 6. 环境变量设置为 0 关闭截断
    monkeypatch.setenv("MCP_RDBMS_MAX_TEXT_LENGTH", "0")
    res_env_zero = SafeSerializer.serialize_value(long_text)
    assert res_env_zero == long_text


