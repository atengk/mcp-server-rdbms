"""
mcp-server-rdbms: 查询结果集与执行计划数据契约定义.

@author Ateng
@since 2026-10-04
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class QueryResult:
    """SQL 只读查询结果集标准契约.

    @author Ateng
    @since 2026-10-04
    """

    row_count: int
    format: Literal["json", "markdown", "csv"]
    data: list[dict[str, Any]] | str
    columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)


@dataclass
class ExplainResult:
    """SQL 执行计划分析结果契约.

    @author Ateng
    @since 2026-10-04
    """

    query: str
    plan: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)
