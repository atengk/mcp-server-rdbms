"""
mcp-server-rdbms: 只读 SQL 查询执行、多格式结果集与慢查询熔断工具.

@author Ateng
@since 2026-10-04
"""

from typing import Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.core.dialect import DialectRegistry
from mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
    SecurityViolationError,
)
from mcp_server_rdbms.core.guard import ASTGuard
from mcp_server_rdbms.core.serializer import SafeSerializer
from mcp_server_rdbms.models.query import ExplainResult, QueryResult


def _execute_query_sync(
    engine: Engine,
    safe_sql: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """在工作线程池中同步执行只读 SQL 查询.

    @param engine: 目标 SQLAlchemy 引擎
    @param safe_sql: 经 AST 语法校验重写后的安全 SQL
    @return: (列名列表, 行字典列表)
    """
    with engine.connect() as conn:
        result = conn.execute(text(safe_sql))
        cols = list(result.keys()) if result.returns_rows else []
        rows = [dict(row._mapping) for row in result.fetchall()] if result.returns_rows else []
        return cols, rows


def _execute_explain_sync(engine: Engine, safe_sql: str) -> list[dict[str, Any]]:
    """在工作线程池中同步获取 SQL 执行计划.

    @param engine: 目标 SQLAlchemy 引擎
    @param safe_sql: 经 AST 纯只读校验的安全 SQL
    @return: 执行计划行字典列表
    """
    prefix = DialectRegistry.get_explain_prefix(engine.dialect.name)
    explain_sql = f"{prefix} {safe_sql}"

    with engine.connect() as conn:
        result = conn.execute(text(explain_sql))
        if result.returns_rows:
            return [dict(row._mapping) for row in result.fetchall()]
        return []


def register_query_tools(server: MCPServer, registry: ConnectionRegistry) -> None:
    """向 FastMCP 服务注册 sql_query 与 sql_explain 工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    """

    @server.tool(
        name="sql_query",
        description="安全执行只读 SQL 查询，支持 json、markdown 表格与 csv 格式输出，具备 AST 校验、自动 LIMIT 注入及慢查询熔断防护。",
    )
    async def sql_query(
        sql: str,
        format: Literal["json", "markdown", "csv"] = "json",
        limit: int = 100,
        timeout: float = 30.0,
        db: str | None = None,
    ) -> dict[str, Any]:
        """安全执行只读数据查询.

        @param sql: 待执行的 SQL 查询语句
        @param format: 结果集渲染格式（json / markdown / csv），默认 json
        @param limit: 缺省 LIMIT 时的安全截断行数，默认 100
        @param timeout: 查询超时阈值（秒），默认 30 秒，最大 120 秒
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 row_count、format、data、columns 的结果字典
        @throws ToolError: 安全违规、超时熔断或执行异常时抛出
        """
        # 1. 超时时限阈值收敛（1 ~ 120 秒）
        timeout_seconds = max(0.001, min(timeout, 120.0))

        try:
            # 2. 获取数据库引擎与方言
            engine = registry.get_engine(db)

            # 3. AST 安全守卫校验与 LIMIT 截断注入
            safe_sql = ASTGuard.validate_and_rewrite_query(
                sql, limit=limit, dialect=engine.dialect.name
            )

            # 4. 线程池异步卸载执行与超时熔断守护
            try:
                with anyio.fail_after(timeout_seconds):
                    cols, rows = await anyio.to_thread.run_sync(
                        _execute_query_sync,
                        engine,
                        safe_sql,
                        abandon_on_cancel=True,
                    )
            except TimeoutError as exc:
                raise ToolError(
                    f"查询执行超时（已超过 {timeout} 秒限制），已触发慢查询熔断保护。"
                ) from exc

            # 5. 安全类型序列化与目标格式渲染
            formatted_data = SafeSerializer.format_rows(rows, format_type=format)

            return QueryResult(
                row_count=len(rows),
                format=format,
                data=formatted_data,
                columns=cols,
            ).to_dict()

        except (SecurityViolationError, DriverMissingError, ConnectionNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise ToolError(f"SQL 查询执行失败: {exc}") from exc

    @server.tool(
        name="sql_explain",
        description="获取指定 SQL 语句的执行计划以辅助分析慢查询原因与索引命中情况。",
    )
    async def sql_explain(
        sql: str,
        db: str | None = None,
    ) -> dict[str, Any]:
        """获取 SQL 执行计划.

        @param sql: 待分析执行计划的 SQL 查询语句
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 query 与 plan 的结果字典
        @throws ToolError: 安全违规或执行计划生成失败时抛出
        """
        try:
            # 1. 获取数据库引擎
            engine = registry.get_engine(db)

            # 2. AST 纯只读性校验（保留原始语句，不强插 LIMIT 影响计划真实性）
            safe_sql = ASTGuard.validate_read_only(sql, dialect=engine.dialect.name)

            # 3. 线程池异步卸载执行 EXPLAIN（配 30 秒熔断防护）
            with anyio.fail_after(30.0):
                plan_rows = await anyio.to_thread.run_sync(
                    _execute_explain_sync,
                    engine,
                    safe_sql,
                    abandon_on_cancel=True,
                )

            # 4. 结果序列化
            serialized_plan = SafeSerializer.serialize_rows(plan_rows)

            return ExplainResult(query=safe_sql, plan=serialized_plan).to_dict()

        except (SecurityViolationError, DriverMissingError, ConnectionNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise ToolError(f"执行计划生成失败: {exc}") from exc
