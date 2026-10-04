"""
mcp-server-rdbms: 数据库基础环境元数据探测工具.

@author Ateng
@since 2026-10-04
"""

import logging
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.core.exceptions import ConnectionNotFoundError, DriverMissingError
from mcp_server_rdbms.models.connection import ConnectionSummary, DatabaseInfo

logger = logging.getLogger(__name__)

# 方言特异性 Schema 查询映射
_SCHEMA_QUERIES: dict[str, str] = {
    "sqlite": "SELECT 'main'",
    "postgresql": "SELECT current_schema()",
    "cockroachdb": "SELECT current_schema()",
    "mysql": "SELECT database()",
    "mariadb": "SELECT database()",
    "oracle": "SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM DUAL",
    "mssql": "SELECT SCHEMA_NAME()",
}

# 方言特异性 User 查询映射
_USER_QUERIES: dict[str, str] = {
    "sqlite": "SELECT 'sqlite'",
    "postgresql": "SELECT current_user",
    "cockroachdb": "SELECT current_user",
    "mysql": "SELECT current_user()",
    "mariadb": "SELECT current_user()",
    "oracle": "SELECT USER FROM DUAL",
    "mssql": "SELECT SUSER_SNAME()",
}


def _safe_query_scalar(conn: Connection, sql: str) -> Any:
    """安全执行单值查询，捕获底层 SQLAlchemy 异常并记录调试日志.

    @param conn: 活跃数据库连接
    @param sql: 待执行的探测 SQL
    @return: 查询结果标量值，执行失败时返回 None
    """
    try:
        return conn.scalar(text(sql))
    except SQLAlchemyError as exc:
        logger.debug("探测查询执行降级 (SQL: %s): %s", sql, exc)
        return None


def fetch_database_info(registry: ConnectionRegistry, db_name: str | None) -> dict[str, Any]:
    """同步获取数据库底层环境信息（全量在工作线程池执行，防阻塞）.

    @param registry: 数据库连接注册表
    @param db_name: 目标数据库别名
    @return: 字典格式的数据库元数据载荷
    """
    profile = registry.get_profile(db_name)
    engine = registry.get_engine(db_name)
    dialect_name = engine.dialect.name
    driver_name = engine.dialect.driver

    with engine.connect() as conn:
        # 1. 获取内核版本信息
        version: str | None = None
        if engine.dialect.server_version_info:
            version = ".".join(str(part) for part in engine.dialect.server_version_info)
        elif dialect_name == "sqlite":
            val = _safe_query_scalar(conn, "SELECT sqlite_version()")
            if val is not None:
                version = str(val)

        if not version:
            val = _safe_query_scalar(conn, "SELECT version()")
            version = str(val) if val is not None else "unknown"

        # 2. 获取当前 Schema 模式
        schema: str | None = engine.dialect.default_schema_name
        if not schema and dialect_name in _SCHEMA_QUERIES:
            val = _safe_query_scalar(conn, _SCHEMA_QUERIES[dialect_name])
            if val is not None:
                schema = str(val)

        # 3. 获取当前登录/活跃用户
        user: str | None = engine.url.username
        if not user and dialect_name in _USER_QUERIES:
            val = _safe_query_scalar(conn, _USER_QUERIES[dialect_name])
            if val is not None:
                user = str(val)

    # 实际数据库名称：优先物理库名，缺省时使用连接配置别名
    db_label = engine.url.database or profile.name

    info_model = DatabaseInfo(
        database=db_label,
        dialect=dialect_name,
        driver=driver_name,
        server_version=version or "unknown",
        current_schema=schema or "unknown",
        current_user=user or "unknown",
        connection=profile.name,
    )
    return info_model.to_dict()


def register_db_info_tool(server: MCPServer, registry: ConnectionRegistry) -> None:
    """向 FastMCP 服务注册 db_get_info 工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    """

    @server.tool(
        name="db_get_info",
        description="获取数据库方言类型、内核版本、当前 Schema 及活跃登录用户等基础环境信息。",
    )
    async def db_get_info(db: str | None = None) -> dict[str, Any]:
        """获取目标数据库基础环境信息.

        @param db: 目标数据库连接别名，缺省时探测默认数据库
        @return: 包含 dialect、driver、server_version、current_schema、current_user 的字典载荷
        """
        try:
            return await anyio.to_thread.run_sync(fetch_database_info, registry, db)
        except (DriverMissingError, ConnectionNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise ToolError(f"数据库执行错误: {exc}") from exc

    @server.tool(
        name="db_list_connections",
        description="查看全部已配置的数据库连接清单，输出连接别名、方言内核、是否为默认库与只读保护属性。连接密码已强制执行安全掩码脱敏 (***)。",
    )
    async def db_list_connections() -> list[dict[str, Any]]:
        """查看所有已注册数据库连接的脱敏清单."""
        profiles = registry.list_profiles()
        return [
            ConnectionSummary(
                name=p.name,
                dialect=p.dialect,
                url=p.masked_url,
                read_only=p.read_only,
                is_default=(p.name == registry.default_alias),
            ).to_dict()
            for p in profiles
        ]
