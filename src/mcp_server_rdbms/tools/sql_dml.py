"""
mcp-server-rdbms: 数据增删改 (DML) 原子事务执行与写权限门禁工具.

@author Ateng
@since 2026-10-04
"""

import time
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from mcp_server_rdbms.core.audit import AuditLogger, audit_logger
from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
    SecurityViolationError,
)
from mcp_server_rdbms.core.guard import ASTGuard
from mcp_server_rdbms.models.audit import AuditEvent
from mcp_server_rdbms.models.dml import DmlResult


def _execute_dml_sync(engine: Engine, statements: list[str]) -> int:
    """在单个数据库原子事务块中执行 DML 语句列表，任何单步失败全量回滚.

    @param engine: 目标 SQLAlchemy 引擎
    @param statements: 经 AST 验证的 DML 语句列表
    @return: 累计受影响行数
    """
    total_rows = 0
    with engine.begin() as conn:
        for stmt in statements:
            res = conn.execute(text(stmt))
            if res.rowcount and res.rowcount > 0:
                total_rows += res.rowcount
    return total_rows


def register_dml_tools(
    server: MCPServer,
    registry: ConnectionRegistry,
    allow_dml: bool = False,
    audit: AuditLogger | None = None,
) -> None:
    """向 FastMCP 服务注册 sql_dml 工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    @param allow_dml: 是否允许执行 DML 操作（默认 False）
    @param audit: 独立审计流水记录器
    """
    active_audit = audit or audit_logger

    @server.tool(
        name="sql_dml",
        description="在单一数据库原子事务中执行单条或批量数据增删改 (DML) 操作。受 --allow-dml 权限门禁保护，任何单步失败全量自动回滚，并在 AST 语法树层强制拦截无 WHERE 条件的 UPDATE 与 DELETE。",
    )
    async def sql_dml(
        sql: str | list[str],
        db: str | None = None,
    ) -> dict[str, Any]:
        """执行数据增删改 (DML) 原子事务.

        @param sql: 单条 SQL 或批量 SQL 语句列表
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 success、statements_executed、rows_affected 的结果字典
        @throws ToolError: 只读保护拦截、安全校验失败或执行回滚时抛出
        """
        start_time = time.perf_counter()
        raw_stmts = [sql] if isinstance(sql, str) else sql
        target_db = db or registry.default_alias

        # 1. 默认只读模式保护门禁检查（遵循 ADR-0003 与安全不变量）
        if not allow_dml:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = (
                "只读模式保护：当前服务未开启数据修改权限。若需执行数据增删改 (DML)，"
                "请在启动服务时显式传入 --allow-dml 参数。"
            )
            event = AuditEvent(
                operation="sql_dml",
                db=target_db,
                statements=raw_stmts,
                status="FAILED",
                duration_ms=duration_ms,
                error=error_msg,
            )
            await active_audit.record_async(event)
            raise ToolError(error_msg)

        # 2. 目标数据库连接独立只读策略检查（遵循 Issue #7 独立只读标志契约）
        if registry.is_read_only(target_db):
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = f"连接只读保护：目标数据库连接 '{target_db}' 处于配置的只读保护状态 (read_only=True)，禁止执行增删改 (DML) 操作。"
            event = AuditEvent(
                operation="sql_dml",
                db=target_db,
                statements=raw_stmts,
                status="FAILED",
                duration_ms=duration_ms,
                error=error_msg,
            )
            await active_audit.record_async(event)
            raise ToolError(error_msg)

        safe_stmts: list[str] = raw_stmts

        try:
            # 3. 获取数据库引擎
            engine = registry.get_engine(db)

            # 3. AST 安全守卫校验（强制拦截无 WHERE 条件的 UPDATE 与 DELETE）
            safe_stmts = ASTGuard.validate_dml_statements(sql, dialect=engine.dialect.name)

            # 4. 线程池异步卸载执行原子事务（单步失败全量自动 ROLLBACK）
            rows_affected = await anyio.to_thread.run_sync(_execute_dml_sync, engine, safe_stmts)

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # 5. 成功审计日志落盘（异步卸载）
            success_event = AuditEvent(
                operation="sql_dml",
                db=target_db,
                statements=safe_stmts,
                status="SUCCESS",
                rows_affected=rows_affected,
                duration_ms=duration_ms,
            )
            await active_audit.record_async(success_event)

            return DmlResult(
                success=True,
                statements_executed=len(safe_stmts),
                rows_affected=rows_affected,
                duration_ms=round(duration_ms, 2),
                message=f"原子事务执行成功，共执行 {len(safe_stmts)} 条语句，累计影响 {rows_affected} 行。",
            ).to_dict()

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            # 6. 失败审计日志全量落盘（包含异常信息与耗时，异步卸载）
            failed_event = AuditEvent(
                operation="sql_dml",
                db=target_db,
                statements=safe_stmts,
                status="FAILED",
                rows_affected=0,
                duration_ms=duration_ms,
                error=str(exc),
            )
            await active_audit.record_async(failed_event)

            if isinstance(exc, (SecurityViolationError, DriverMissingError, ConnectionNotFoundError)):
                raise ToolError(str(exc)) from exc
            if isinstance(exc, SQLAlchemyError):
                raise ToolError(f"DML 原子事务执行失败，已自动全量回滚: {exc}") from exc
            raise
