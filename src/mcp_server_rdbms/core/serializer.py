"""
mcp-server-rdbms: 复杂非标类型安全序列化与多格式结果集适配器.

@author Ateng
@since 2026-10-04
"""

import csv
import io
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal


class SafeSerializer:
    """安全序列化器：转换 Decimal/时间/UUID、截断大 BLOB 并格式化多类型结果集.

    @author Ateng
    @since 2026-10-04
    """

    @classmethod
    def serialize_value(cls, val: Any) -> Any:
        """递归安全序列化单个值对象.

        @param val: 任意待序列化对象
        @return: JSON/文本友好的 Python 原生对象
        """
        if val is None:
            return None

        # 1. 浮点与定点 Decimal
        if isinstance(val, Decimal):
            if val % 1 == 0:
                return int(val)
            return float(val)

        # 2. 日期与时间对象
        if isinstance(val, (datetime, date, time)):
            return val.isoformat()

        # 3. UUID 对象
        if isinstance(val, uuid.UUID):
            return str(val)

        # 4. 二进制对象截断与转换（遵循 ADR-0005，大于 1KB 截断）
        if isinstance(val, (bytes, bytearray, memoryview)):
            raw_bytes = bytes(val)
            byte_len = len(raw_bytes)
            if byte_len <= 1024:
                return raw_bytes.hex()
            preview = raw_bytes[:16].hex()
            return f"<BLOB {byte_len} bytes: {preview}...[truncated]>"

        # 5. 字典容器递归处理
        if isinstance(val, dict):
            return {str(k): cls.serialize_value(v) for k, v in val.items()}

        # 6. 列表与集合容器递归处理
        if isinstance(val, (list, tuple, set)):
            return [cls.serialize_value(item) for item in val]

        # 7. 基础原生字面量保持原样
        if isinstance(val, (int, float, bool, str)):
            return val

        # 8. 其余未知对象兜底转为字符串
        return str(val)

    @classmethod
    def serialize_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """批量序列化行数据字典列表（空列表返回 []）.

        @param rows: 原始行字典列表
        @return: 序列化后的行字典列表
        """
        if not rows:
            return []
        return [cls.serialize_value(r) for r in rows]

    @classmethod
    def format_rows(
        cls,
        rows: list[dict[str, Any]],
        format_type: Literal["json", "markdown", "csv"] = "json",
    ) -> list[dict[str, Any]] | str:
        """将结果集行数据根据目标格式渲染为对应载荷.

        @param rows: 原始行字典列表
        @param format_type: 目标格式（json / markdown / csv）
        @return: 目标格式载荷（list 或 str）
        """
        if not rows:
            if format_type == "json":
                return []
            if format_type == "markdown":
                return "(0 行数据)"
            if format_type == "csv":
                return ""

        serialized = cls.serialize_rows(rows)

        if format_type == "json":
            return serialized

        headers = list(serialized[0].keys())

        if format_type == "markdown":
            lines: list[str] = []
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in serialized:
                row_vals = [
                    str(row.get(h, "")).replace("|", "\\|").replace("\n", " ") for h in headers
                ]
                lines.append("| " + " | ".join(row_vals) + " |")
            return "\n".join(lines)

        if format_type == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
            writer.writeheader()
            writer.writerows(serialized)
            return output.getvalue()

        return serialized
