"""
mcp-server-rdbms: 数据库模式、表清单与表结构元数据契约定义.

@author Ateng
@since 2026-10-04
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class TableSummary:
    """单一数据表或视图摘要.

    @author Ateng
    @since 2026-10-04
    """

    name: str
    type: Literal["table", "view"] = "table"
    comment: str | None = None


@dataclass
class ForeignKeyTopology:
    """数据表间外键约束拓扑关系.

    @author Ateng
    @since 2026-10-04
    """

    constrained_table: str
    constrained_columns: list[str]
    referred_table: str
    referred_columns: list[str]
    referred_schema: str | None = None
    name: str | None = None


@dataclass
class ColumnDetail:
    """数据表列字段全息定义明细.

    @author Ateng
    @since 2026-10-04
    """

    name: str
    type: str
    nullable: bool
    default: str | None = None
    primary_key: bool = False
    comment: str | None = None


@dataclass
class IndexDetail:
    """索引定义明细.

    @author Ateng
    @since 2026-10-04
    """

    name: str
    columns: list[str] = field(default_factory=list)
    unique: bool = False


@dataclass
class TableDetail:
    """单一数据表一站式全息结构明细.

    @author Ateng
    @since 2026-10-04
    """

    table_name: str
    schema: str | None
    columns: list[ColumnDetail] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKeyTopology] = field(default_factory=list)
    indexes: list[IndexDetail] = field(default_factory=list)
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)


@dataclass
class TableListResult:
    """数据表清单与全库外键拓扑结果契约.

    @author Ateng
    @since 2026-10-04
    """

    schema: str | None
    tables: list[TableSummary] = field(default_factory=list)
    foreign_keys: list[ForeignKeyTopology] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)
