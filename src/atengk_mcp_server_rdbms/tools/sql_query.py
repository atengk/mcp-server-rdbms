"""
mcp-server-rdbms: 只读 SQL 查询执行、多格式结果集与慢查询熔断工具.

@author Ateng
@since 2026-10-04
"""

import time
from typing import Any, Literal

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from atengk_mcp_server_rdbms.core.audit import AuditLogger, audit_logger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.dialect import DialectRegistry
from atengk_mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
    SecurityViolationError,
)
from atengk_mcp_server_rdbms.core.guard import ASTGuard
from atengk_mcp_server_rdbms.core.serializer import SafeSerializer
from atengk_mcp_server_rdbms.models.query import QueryResult


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


def _execute_explain_sync(
    engine: Engine,
    safe_sql: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """在工作线程池中同步获取 SQL 执行计划.

    @param engine: 目标 SQLAlchemy 引擎
    @param safe_sql: 经 AST 纯只读校验的安全 SQL
    @return: (列名列表, 执行计划行字典列表)
    """
    prefix = DialectRegistry.get_explain_prefix(engine.dialect.name)
    explain_sql = f"{prefix} {safe_sql}"

    with engine.connect() as conn:
        result = conn.execute(text(explain_sql))
        cols = list(result.keys()) if result.returns_rows else []
        rows = [dict(row._mapping) for row in result.fetchall()] if result.returns_rows else []
        return cols, rows


def register_query_tools(
    server: MCPServer,
    registry: ConnectionRegistry,
    audit: AuditLogger | None = None,
) -> None:
    """向 FastMCP 服务注册 sql_query 与 sql_explain 工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    @param audit: 独立审计流水记录器
    """
    active_audit = audit or audit_logger

    @server.tool(
        name="sql_query",
        description="安全执行只读 SQL 查询或获取执行计划。在初次探索未知业务表时，强烈建议显式指定 limit=3~5 获取结构样本；未显式指定 limit 时系统底层将安全截断至 100 行。支持 json、markdown 表格与 csv 格式输出，具备 AST 校验及慢查询熔断防护；支持 explain=True 获取执行计划分析慢查询。",
    )
    async def sql_query(
        sql: str,
        explain: bool = False,
        format: Literal["json", "markdown", "csv"] = "json",
        limit: int = 100,
        timeout: float = 30.0,
        db: str | None = None,
    ) -> dict[str, Any]:
        """安全执行只读数据查询或执行计划分析.

        @param sql: 待执行的 SQL 查询语句
        @param explain: 是否以执行计划模式运行（默认 False），开启时不注入 LIMIT 且拦截 ANALYZE/EXECUTE 危险修饰符
        @param format: 结果集渲染格式（json / markdown / csv），默认 json
        @param limit: 缺省 LIMIT 时的安全截断行数，默认 100（仅在 explain=False 时生效）
        @param timeout: 查询超时阈值（秒），默认 30 秒，最大 120 秒
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 row_count、format、data、columns、truncated 的结果字典
        @throws ToolError: 安全违规、超时熔断或执行异常时抛出
        """
        # 1. 超时时限阈值收敛（1 ~ 120 秒）
        timeout_seconds = max(0.001, min(timeout, 120.0))
        start_time = time.perf_counter()
        target_db = db or registry.default_alias or "default"

        try:
            # 2. 获取数据库引擎与方言
            engine = registry.get_engine(db)

            # 3. 根据 explain 模式选择 AST 安全校验与执行通道
            if explain:
                # 执行计划模式：专用校验通道，剥离危险修饰符且绝对不追加外层 LIMIT
                safe_sql = ASTGuard.validate_explain_query(sql, dialect=engine.dialect.name)
                try:
                    with anyio.fail_after(timeout_seconds):
                        cols, rows = await anyio.to_thread.run_sync(
                            _execute_explain_sync,
                            engine,
                            safe_sql,
                            abandon_on_cancel=True,
                        )
                except TimeoutError as exc:
                    raise ToolError(
                        f"执行计划生成超时（已超过 {timeout} 秒限制），已触发慢查询熔断保护。"
                    ) from exc
            else:
                # 普通只读模式：AST 安全守卫校验与 LIMIT 截断注入
                safe_sql = ASTGuard.validate_and_rewrite_query(
                    sql, limit=limit, dialect=engine.dialect.name
                )
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

            # 4. 安全类型序列化与目标格式渲染
            formatted_data = SafeSerializer.format_rows(rows, format_type=format)
            is_truncated = (not explain) and (len(rows) >= limit)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            await active_audit.record_async(
                operation="sql_query",
                db=target_db,
                statements=[sql],
                status="SUCCESS",
                rows_affected=len(rows),
                duration_ms=duration_ms,
            )

            return QueryResult(
                row_count=len(rows),
                format=format,
                data=formatted_data,
                columns=cols,
                truncated=is_truncated,
            ).to_dict()

        except (SecurityViolationError, DriverMissingError, ConnectionNotFoundError) as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            await active_audit.record_async(
                operation="sql_query",
                db=target_db,
                statements=[sql],
                status="FAILED",
                rows_affected=0,
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise ToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            await active_audit.record_async(
                operation="sql_query",
                db=target_db,
                statements=[sql],
                status="FAILED",
                rows_affected=0,
                duration_ms=duration_ms,
                error=str(exc),
            )
            err_label = "执行计划生成失败" if explain else "SQL 查询执行失败"
            raise ToolError(f"{err_label}: {exc}") from exc
        except ToolError as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            await active_audit.record_async(
                operation="sql_query",
                db=target_db,
                statements=[sql],
                status="FAILED",
                rows_affected=0,
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise

