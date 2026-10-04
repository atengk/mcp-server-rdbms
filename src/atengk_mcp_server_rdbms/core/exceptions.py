"""
mcp-server-rdbms: 核心领域自定义异常定义.

@author Ateng
@since 2026-10-04
"""


class RdbmsMcpError(Exception):
    """关系型数据库 MCP 服务通用基础异常."""


class DriverMissingError(RdbmsMcpError):
    """目标数据库驱动或方言扩展缺失异常."""

    def __init__(self, message: str, dialect: str | None = None, driver: str | None = None) -> None:
        super().__init__(message)
        self.dialect = dialect
        self.driver = driver


class ConnectionNotFoundError(RdbmsMcpError):
    """未找到指定的数据库连接配置异常.

    @author Ateng
    @since 2026-10-04
    """

    def __init__(self, connection_name: str) -> None:
        super().__init__(f"未找到指定的数据库连接配置: '{connection_name}'")
        self.connection_name = connection_name


class TableNotFoundError(RdbmsMcpError):
    """指定的数据表不存在异常.

    @author Ateng
    @since 2026-10-04
    """

    def __init__(self, table_name: str, schema: str | None = None) -> None:
        schema_hint = f"模式 '{schema}' 中的" if schema else ""
        super().__init__(f"未找到{schema_hint}数据表: '{table_name}'")
        self.table_name = table_name
        self.schema = schema


class SecurityViolationError(RdbmsMcpError):
    """SQL 安全守卫拦截违规异常.

    @author Ateng
    @since 2026-10-04
    """


class QueryTimeoutError(RdbmsMcpError):
    """慢查询执行超时熔断异常.

    @author Ateng
    @since 2026-10-04
    """


class ConfigurationError(RdbmsMcpError):
    """服务配置错误或连接串解析异常."""
