"""
mcp-server-rdbms: 数据库写操作与变更独立审计流水记录器及日志切片.

@author Ateng
@since 2026-10-04
"""

import threading
from functools import partial
from pathlib import Path
from typing import Literal

import anyio

from mcp_server_rdbms.models.audit import AuditEvent


class AuditLogger:
    """写操作独立审计流水记录器：全量落盘 DML 与 DDL 执行记录至本地日志文件，支持大小切片轮转.

    @author Ateng
    @since 2026-10-04
    """

    DEFAULT_LOG_FILE: str = "rdbms_mcp_audit.log"
    # 默认单文件 10MB 触发切片轮转，保留 5 个历史切片
    DEFAULT_MAX_BYTES: int = 10 * 1024 * 1024
    DEFAULT_BACKUP_COUNT: int = 5

    def __init__(
        self,
        log_file: str | Path | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
    ) -> None:
        """初始化审计记录器.

        @param log_file: 审计日志文件路径
        @param max_bytes: 单个日志文件最大字节数，超过时触发切片
        @param backup_count: 保留的历史日志切片副本数量
        """
        self.log_path = Path(log_file or self.DEFAULT_LOG_FILE)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.Lock()

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
        """同步记录一条数据变更审计流水（支持 AuditEvent 实体或关键字参数传值）.

        @param event: AuditEvent 实例或操作名称（如 sql_dml 或 sql_ddl）
        @param operation: 操作名称（关键字参数）
        @param db: 目标数据库别名
        @param statements: 执行的 SQL 语句列表
        @param status: 执行状态（SUCCESS 或 FAILED）
        @param rows_affected: 受影响数据行数
        @param duration_ms: 操作耗时（毫秒）
        @param error: 异常错误描述（失败时传入）
        """
        if isinstance(event, AuditEvent):
            audit_event = event
        elif isinstance(event, str):
            audit_event = AuditEvent(
                operation=event,
                db=db or "default",
                statements=statements or [],
                status=status or "SUCCESS",
                rows_affected=rows_affected,
                duration_ms=duration_ms,
                error=error,
            )
        else:
            audit_event = AuditEvent(
                operation=operation or "unknown",
                db=db or "default",
                statements=statements or [],
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


# 全局默认审计记录器单例
audit_logger = AuditLogger()
