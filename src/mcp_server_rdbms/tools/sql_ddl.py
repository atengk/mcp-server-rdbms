"""
mcp-server-rdbms: 表结构定义变更 (DDL) 安全执行与权限门禁工具.

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
from mcp_server_rdbms.models.ddl import DdlResult


def _execute_ddl_sync(engine: Engine, statement: str) -> None:
    """同步执行 DDL 语句并提交变更.

    @param engine: 目标 SQLAlchemy 引擎
    @param statement: 经 AST 验证的 DDL 语句
    """
    with engine.connect() as conn:
        conn.execute(text(statement))
        conn.commit()


def register_ddl_tools(
    server: MCPServer,
    registry: ConnectionRegistry,
    allow_ddl: bool = False,
    audit: AuditLogger | None = None,
) -> None:
    """向 FastMCP 服务注册 sql_ddl 工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    @param allow_ddl: 是否允许执行 DDL 操作（默认 False）
    @param audit: 独立审计流水记录器
    """
    active_audit = audit or audit_logger

    @server.tool(
        name="sql_ddl",
        description="执行表结构定义变更 (DDL)，包含建表、改表、删表与表截断。受 --allow-ddl 权限门禁与 confirm=True 显式确认双重保护，并全量落盘独立审计流水。",
    )
    async def sql_ddl(
        sql: str,
        confirm: bool = False,
        db: str | None = None,
    ) -> dict[str, Any]:
        """执行表结构定义变更 (DDL).

        @param sql: 单条 DDL 语句（如 CREATE TABLE, ALTER TABLE, DROP TABLE）
        @param confirm: 破坏性操作显式二次确认（必须为 True 才能执行）
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 success、statement、duration_ms、message 的结果字典
        @throws ToolError: 只读保护拦截、未二次确认、安全校验失败或执行报错时抛出
        """
        start_time = time.perf_counter()
        target_db = db or registry.default_alias

        # 1. 默认权限门禁检查（遵循 ADR-0003 与安全不变量）
        if not allow_ddl:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = (
                "只读模式保护：当前服务未开启结构定义变更权限。若需执行建表、改表或删表 (DDL)，"
                "请在启动服务时显式传入 --allow-ddl 参数。"
            )
            event = AuditEvent(
                operation="sql_ddl",
                db=target_db,
                statements=[sql],
                status="FAILED",
                duration_ms=duration_ms,
                error=error_msg,
            )
            await active_audit.record_async(event)
            raise ToolError(error_msg)

        # 2. 显式破坏性操作二次确认保护
        if not confirm:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = (
                "二次确认保护：执行结构定义变更 (DDL) 具有不可逆破坏性，"
                "请显式传入 confirm=True 以确认执行。"
            )
            event = AuditEvent(
                operation="sql_ddl",
                db=target_db,
                statements=[sql],
                status="FAILED",
                duration_ms=duration_ms,
                error=error_msg,
            )
            await active_audit.record_async(event)
            raise ToolError(error_msg)

        # 3. 目标数据库连接独立只读策略检查（遵循 Issue #7 独立只读标志契约）
        if registry.is_read_only(target_db):
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = f"连接只读保护：目标数据库连接 '{target_db}' 处于配置的只读保护状态 (read_only=True)，禁止执行结构定义变更 (DDL) 操作。"
            event = AuditEvent(
                operation="sql_ddl",
                db=target_db,
                statements=[sql],
                status="FAILED",
                duration_ms=duration_ms,
                error=error_msg,
            )
            await active_audit.record_async(event)
            raise ToolError(error_msg)

        safe_sql: str = sql

        try:
            # 4. 获取数据库引擎
            engine = registry.get_engine(db)

            # 4. AST 语法树安全校验（确保纯 DDL，拦截非 DDL 与多语句注入）
            safe_sql = ASTGuard.validate_ddl_statement(sql, dialect=engine.dialect.name)

            # 5. 线程池异步卸载执行 DDL 语句
            await anyio.to_thread.run_sync(_execute_ddl_sync, engine, safe_sql)

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # 6. 成功审计日志落盘（异步卸载）
            success_event = AuditEvent(
                operation="sql_ddl",
                db=target_db,
                statements=[safe_sql],
                status="SUCCESS",
                rows_affected=0,
                duration_ms=duration_ms,
            )
            await active_audit.record_async(success_event)

            return DdlResult(
                success=True,
                statement=safe_sql,
                duration_ms=round(duration_ms, 2),
                message="DDL 结构定义变更执行成功。",
            ).to_dict()

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            # 7. 失败审计日志全量落盘（包含异常信息与耗时，异步卸载）
            failed_event = AuditEvent(
                operation="sql_ddl",
                db=target_db,
                statements=[safe_sql],
                status="FAILED",
                rows_affected=0,
                duration_ms=duration_ms,
                error=str(exc),
            )
            await active_audit.record_async(failed_event)

            if isinstance(exc, (SecurityViolationError, DriverMissingError, ConnectionNotFoundError)):
                raise ToolError(str(exc)) from exc
            if isinstance(exc, SQLAlchemyError):
                raise ToolError(f"DDL 结构定义变更执行失败: {exc}") from exc
            raise
