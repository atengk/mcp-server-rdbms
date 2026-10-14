"""
mcp-server-rdbms: 数据库写操作与变更独立审计流水记录器及日志切片.

@author Ateng
@since 2026-10-04
"""

import threading
from functools import partial
from pathlib import Path
from typing import Any, Literal

import anyio

from atengk_mcp_server_rdbms.models.audit import AuditEvent


class AuditLogger:
    """分级操作独立审计流水记录器：全量落盘 DML、DDL 及只读查询执行记录至本地日志文件，支持大小切片轮转与防爆截断.

    @author Ateng
    @since 2026-10-04
    """

    DEFAULT_LOG_FILE: str = "rdbms_mcp_audit.log"
    # 默认单文件 10MB 触发切片轮转，保留 5 个历史切片
    DEFAULT_MAX_BYTES: int = 10 * 1024 * 1024
    DEFAULT_BACKUP_COUNT: int = 5
    DEFAULT_MAX_STMT_CHARS: int = 4096
    DEFAULT_MAX_STATEMENTS: int = 100

    def __init__(
        self,
        log_file: str | Path | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        mode: Literal["mutation", "all", "off"] | str = "mutation",
        max_stmt_chars: int = DEFAULT_MAX_STMT_CHARS,
        max_statements: int = DEFAULT_MAX_STATEMENTS,
    ) -> None:
        """初始化审计记录器.

        @param log_file: 审计日志文件路径
        @param max_bytes: 单个日志文件最大字节数，超过时触发切片
        @param backup_count: 保留的历史日志切片副本数量
        @param mode: 审计模式（mutation: 仅变更, all: 全量包含查询, off: 关闭）
        @param max_stmt_chars: 单条语句最大允许记录字符数，超长自动截断
        @param max_statements: 批量语句最大记录条数，超量自动截断
        """
        self.log_path = Path(log_file or self.DEFAULT_LOG_FILE)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        normalized_mode = str(mode).lower().strip()
        self.mode: Literal["mutation", "all", "off"] = (
            normalized_mode if normalized_mode in {"mutation", "all", "off"} else "mutation"  # type: ignore[assignment]
        )
        self.max_stmt_chars = max_stmt_chars
        self.max_statements = max_statements
        self._lock = threading.Lock()

    def should_record(self, operation: str) -> bool:
        """判定指定操作在当前审计模式下是否应予记录.

        @param operation: 工具或操作名称（如 sql_dml, sql_ddl, sql_query）
        @return: True 为应记录，False 为跳过
        """
        if self.mode == "off":
            return False
        if self.mode == "all":
            return True
        # mutation 模式仅审计写变更
        return operation in {"sql_dml", "sql_ddl"}

    def sanitize_statements(self, statements: list[str]) -> list[str]:
        """对执行的 SQL 语句列表进行防爆截断处理，防止大字段或批量洪峰击穿磁盘.

        @param statements: 待记录的原始 SQL 列表
        @return: 经截断防护后的安全 SQL 列表
        """
        if not statements:
            return []

        cleaned: list[str] = []
        truncated_count = 0
        total = len(statements)

        target_stmts = statements
        if total > self.max_statements:
            target_stmts = statements[: self.max_statements]
            truncated_count = total - self.max_statements

        for stmt in target_stmts:
            if len(stmt) > self.max_stmt_chars:
                # 保留前 2048 字符与后 1024 字符
                head = stmt[:2048]
                tail = stmt[-1024:]
                omitted = len(stmt) - 3072
                cleaned.append(f"{head}...[TRUNCATED {omitted} chars]...{tail}")
            else:
                cleaned.append(stmt)

        if truncated_count > 0:
            cleaned.append(
                f"[TRUNCATED: {truncated_count} statements omitted, total: {total}]"
            )

        return cleaned

    def _rotate_if_needed(self, incoming_bytes_len: int) -> None:
        """检查并执行日志切片轮转 (Log Rotation).

        当当前日志大小加上新增写入大小超过 max_bytes 时，
        将现有切片依次向后移动：`audit.log.N-1` -> `audit.log.N`，最后将 `audit.log` 移为 `audit.log.1`。
        """
        if self.max_bytes <= 0 or not self.log_path.exists():
            return

        current_size = self.log_path.stat().st_size
        if current_size + incoming_bytes_len <= self.max_bytes:
            return

        # 1. 滚动已有的历史切片
        for i in range(self.backup_count - 1, 0, -1):
            sfn = self.log_path.with_name(f"{self.log_path.name}.{i}")
            dfn = self.log_path.with_name(f"{self.log_path.name}.{i + 1}")
            if sfn.exists():
                if dfn.exists():
                    dfn.unlink()
                sfn.rename(dfn)

        # 2. 将当前活动日志重命名为 .1 切片
        dfn = self.log_path.with_name(f"{self.log_path.name}.1")
        if dfn.exists():
            dfn.unlink()
        self.log_path.rename(dfn)

    def record(
        self,
        event: AuditEvent | str | None = None,
        *,
        operation: str | None = None,
        db: str | None = None,
        statements: list[str] | None = None,
        status: Literal["SUCCESS", "FAILED"] | None = None,
        rows_affected: int = 0,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        """同步记录一条数据操作审计流水（支持 AuditEvent 实体或关键字参数传值）.

        @param event: AuditEvent 实例或操作名称（如 sql_dml, sql_ddl, sql_query）
        @param operation: 操作名称（关键字参数）
        @param db: 目标数据库别名
        @param statements: 执行的 SQL 语句列表
        @param status: 执行状态（SUCCESS 或 FAILED）
        @param rows_affected: 受影响数据行数
        @param duration_ms: 操作耗时（毫秒）
        @param error: 异常错误描述（失败时传入）
        """
        target_op = ""
        if isinstance(event, AuditEvent):
            target_op = event.operation
        elif isinstance(event, str):
            target_op = event
        else:
            target_op = operation or "unknown"

        if not self.should_record(target_op):
            return

        if isinstance(event, AuditEvent):
            sanitized_stmts = self.sanitize_statements(event.statements)
            audit_event = event.model_copy(update={"statements": sanitized_stmts})
        elif isinstance(event, str):
            audit_event = AuditEvent(
                operation=event,
                db=db or "default",
                statements=self.sanitize_statements(statements or []),
                status=status or "SUCCESS",
                rows_affected=rows_affected,
                duration_ms=duration_ms,
                error=error,
            )
        else:
            audit_event = AuditEvent(
                operation=operation or "unknown",
                db=db or "default",
                statements=self.sanitize_statements(statements or []),
                status=status or "SUCCESS",
                rows_affected=rows_affected,
                duration_ms=duration_ms,
                error=error,
            )

        line = audit_event.model_dump_json() + "\n"
        raw_bytes = line.encode("utf-8")

        with self._lock:
            # 确保父级目录存在
            if self.log_path.parent and not self.log_path.parent.exists():
                self.log_path.parent.mkdir(parents=True, exist_ok=True)

            # 检查并执行切片轮转
            self._rotate_if_needed(len(raw_bytes))

            # 追加写入
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)

    async def record_async(
        self,
        event: AuditEvent | str | None = None,
        *,
        operation: str | None = None,
        db: str | None = None,
        statements: list[str] | None = None,
        status: Literal["SUCCESS", "FAILED"] | None = None,
        rows_affected: int = 0,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        """异步卸载执行审计流水落盘，防止阻塞 FastMCP 事件循环."""
        func = partial(
            self.record,
            event,
            operation=operation,
            db=db,
            statements=statements,
            status=status,
            rows_affected=rows_affected,
            duration_ms=duration_ms,
            error=error,
        )
        await anyio.to_thread.run_sync(func)

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取最近落盘的审计事件列表（按发生时间由新到旧倒序返回）.

        @param limit: 最多返回的记录条数（默认 50 条）
        @return: 审计事件字典列表
        """
        if not self.log_path.exists():
            return []

        import json

        events: list[dict[str, Any]] = []
        with self._lock:
            try:
                with open(self.log_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        events.append(json.loads(line_str))
                        if len(events) >= limit:
                            break
                    except (json.JSONDecodeError, ValueError):
                        pass
            except OSError:
                return []
        return events

    async def get_recent_events_async(self, limit: int = 50) -> list[dict[str, Any]]:
        """异步安全读取最近审计流水，防止阻塞 FastMCP 事件循环."""
        return await anyio.to_thread.run_sync(partial(self.get_recent_events, limit))


# 全局默认审计记录器单例
audit_logger = AuditLogger()
