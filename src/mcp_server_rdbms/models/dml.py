"""
mcp-server-rdbms: 数据增删改 (DML) 执行结果契约定义.

@author Ateng
@since 2026-10-04
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DmlResult:
    """DML 原子事务操作执行结果契约.

    @author Ateng
    @since 2026-10-04
    """

    success: bool
    statements_executed: int
    rows_affected: int
    duration_ms: float
    message: str = "执行成功"

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)
