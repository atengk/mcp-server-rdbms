"""
mcp-server-rdbms: 数据库系统保留模式与内置表过滤器.

@author Ateng
@since 2026-10-04
"""

from typing import ClassVar


class SchemaFilter:
    """模式与系统表过滤器：排除数据库底层系统保留模式与内置元数据表.

    @author Ateng
    @since 2026-10-04
    """

    # 各主流数据库常见系统保留模式（统一转小写匹配）
    _SYSTEM_SCHEMAS: ClassVar[set[str]] = {
        # PostgreSQL / CockroachDB
        "pg_catalog",
        "pg_toast",
        "information_schema",
        # MySQL / MariaDB
        "performance_schema",
        "mysql",
        "sys",
        # SQL Server
        "guest",
        # Oracle
        "system",
        "outln",
        "dbsnmp",
        "appqossys",
        "wmsys",
        "ctxsys",
        "xdb",
        "anonymous",
        "mdsys",
        "olapsys",
        "lbacsys",
        "dvsys",
    }

    @classmethod
    def is_system_schema(cls, schema_name: str | None) -> bool:
        """判断指定 Schema 是否为系统保留内置模式.

        @param schema_name: Schema 名称
        @return: 是否为系统模式
        """
        if not schema_name:
            return False
        return schema_name.lower() in cls._SYSTEM_SCHEMAS

    @classmethod
    def is_system_table(cls, table_name: str, dialect: str = "") -> bool:
        """判断指定数据表是否为系统内部保留表.

        @param table_name: 数据表名
        @param dialect: 数据库方言标识
        @return: 是否为系统内部保留表
        """
        lower_name = table_name.lower()
        if dialect == "sqlite":
            return lower_name.startswith("sqlite_")
        return False

    @classmethod
    def filter_tables(cls, tables: list[str], dialect: str = "") -> list[str]:
        """过滤给定的表名列表，排除系统内置表.

        @param tables: 待过滤表名列表
        @param dialect: 数据库方言标识
        @return: 过滤后的业务表名列表（无匹配时返回空列表 []）
        """
        if not tables:
            return []
        return [t for t in tables if not cls.is_system_table(t, dialect=dialect)]
