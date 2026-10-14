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

    def __init__(
        self,
        connection_name: str,
        available_profiles: list[str] | None = None,
    ) -> None:
        self.connection_name = connection_name
        self.available_profiles = available_profiles or []
        avail_hint = (
            f"。当前已注册可用连接清单: {self.available_profiles}。💡 自愈指引：请通过 db 参数指定有效连接别名，或读取 MCP 只读资源 rdbms://connections 预先查看已配置连接。"
            if self.available_profiles
            else "。"
        )
        super().__init__(f"未找到指定的数据库连接配置: '{connection_name}'{avail_hint}")


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
