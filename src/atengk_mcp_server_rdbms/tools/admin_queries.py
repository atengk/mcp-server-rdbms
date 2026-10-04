"""
mcp-server-rdbms: 数据库活动进程与长查询运维观测工具.

@author Ateng
@since 2026-10-04
"""

from collections.abc import Mapping
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
)
from atengk_mcp_server_rdbms.models.admin import RunningQueriesResult, RunningQuery

# 各方言活动查询系统探查 SQL 策略表
_DIALECT_RUNNING_QUERY_SQL: dict[str, str] = {
    "postgresql": """
        SELECT
            pid,
            usename AS "user",
            datname AS "db",
            ROUND(EXTRACT(EPOCH FROM (now() - query_start))::numeric, 2) AS duration_seconds,
            state,
            query
        FROM pg_stat_activity
        WHERE state IS NOT NULL
          AND state != 'idle'
          AND pid != pg_backend_pid()
        ORDER BY duration_seconds DESC NULLS LAST
        LIMIT 50
    """,
    "postgres": """
        SELECT
            pid,
            usename AS "user",
            datname AS "db",
            ROUND(EXTRACT(EPOCH FROM (now() - query_start))::numeric, 2) AS duration_seconds,
            state,
            query
        FROM pg_stat_activity
        WHERE state IS NOT NULL
          AND state != 'idle'
          AND pid != pg_backend_pid()
        ORDER BY duration_seconds DESC NULLS LAST
        LIMIT 50
    """,
    "mysql": """
        SELECT
            id AS pid,
            user,
            db,
            time AS duration_seconds,
            command AS state,
            info AS query
        FROM information_schema.processlist
        WHERE command != 'Sleep'
          AND id != connection_id()
        ORDER BY time DESC
        LIMIT 50
    """,
    "mariadb": """
        SELECT
            id AS pid,
            user,
            db,
            time AS duration_seconds,
            command AS state,
            info AS query
        FROM information_schema.processlist
        WHERE command != 'Sleep'
          AND id != connection_id()
        ORDER BY time DESC
        LIMIT 50
    """,
}


def _safe_float(val: Any) -> float | None:
    """防御性转换浮点数."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _map_row_to_query(row: Mapping[str, Any]) -> RunningQuery:
    """提取行映射字段组装 RunningQuery 实体."""
    return RunningQuery(
        pid=row.get("pid"),
        user=row.get("user"),
        db=row.get("db"),
        duration_seconds=_safe_float(row.get("duration_seconds")),
        state=row.get("state"),
        query=row.get("query"),
    )


def _query_running_queries_sync(engine: Engine) -> RunningQueriesResult:
    """在工作线程中同步探查当前数据库的活动查询进程列表.

    @param engine: 目标 SQLAlchemy 引擎
    @return: 结构化活动查询观测结果（支持自适应优雅降级）
    """
    dialect_name = engine.dialect.name.lower()

    # 1. 对轻量内嵌库（如 SQLite）自适应优雅降级
    if dialect_name == "sqlite":
        return RunningQueriesResult(
            supported=False,
            dialect="sqlite",
            queries=[],
            message="SQLite 是单进程内嵌轻量数据库，不支持服务端活动进程与长查询观测 (pg_stat_activity / processlist)。",
        )

    # 2. 匹配已支持方言的系统查询 SQL
    sql_tpl = _DIALECT_RUNNING_QUERY_SQL.get(dialect_name)
    if sql_tpl:
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql_tpl))
                queries = [_map_row_to_query(row) for row in result.mappings()]
                return RunningQueriesResult(
                    supported=True,
                    dialect=dialect_name,
                    queries=queries,
                    message=f"成功观测到 {len(queries)} 个活动查询进程。",
                )
        except SQLAlchemyError as exc:
            return RunningQueriesResult(
                supported=False,
                dialect=dialect_name,
                queries=[],
                message=f"查询活动进程系统视图失败（可能缺少监控视图访问权限）: {exc}",
            )

    # 3. 其他未知或未配置方言自适应降级
    return RunningQueriesResult(
        supported=False,
        dialect=dialect_name,
        queries=[],
        message=f"当前数据库方言 ({dialect_name}) 暂未配置进程观测系统视图，自适应跳过观测。",
    )


def register_admin_tools(
    server: MCPServer,
    registry: ConnectionRegistry,
) -> None:
    """向 FastMCP 服务注册运维观测类工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    """

    @server.tool(
        name="admin_list_running_queries",
        description="观测数据库当前正在执行的活动进程与慢查询。对 PostgreSQL、MySQL 等支持进程视图的数据库返回明细，对 SQLite 等内嵌库自适应优雅降级并返回友好说明。",
    )
    async def admin_list_running_queries(
        db: str | None = None,
    ) -> dict[str, Any]:
        """获取目标数据库的活动查询进程列表.

        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 supported、dialect、queries、message 的观测结果字典
        @throws ToolError: 目标连接不存在或驱动缺失时抛出
        """
        try:
            engine = registry.get_engine(db)
            result = await anyio.to_thread.run_sync(_query_running_queries_sync, engine)
            return result.to_dict()
        except (DriverMissingError, ConnectionNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            raise ToolError(f"观测数据库活动查询失败: {exc}") from exc
