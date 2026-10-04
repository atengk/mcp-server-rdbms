"""
mcp-server-rdbms: 独立审计流水记录器与日志切片轮转测试.

@author Ateng
@since 2026-10-04
"""

import json
from pathlib import Path

import pytest

from mcp_server_rdbms.core.audit import AuditLogger
from mcp_server_rdbms.models.audit import AuditEvent


def test_audit_logger_records_success(tmp_path: Path):
    log_file = tmp_path / "test_audit.log"
    logger = AuditLogger(log_file=str(log_file))

    logger.record(
        operation="sql_dml",
        db="default",
        statements=["UPDATE users SET score = 100 WHERE id = 1"],
        status="SUCCESS",
        rows_affected=1,
        duration_ms=15.2,
    )

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8").strip()
    entry = json.loads(content)

    assert entry["operation"] == "sql_dml"
    assert entry["db"] == "default"
    assert entry["status"] == "SUCCESS"
    assert entry["rows_affected"] == 1
    assert entry["duration_ms"] == 15.2
    assert "UPDATE users SET score = 100 WHERE id = 1" in entry["statements"][0]
    assert "timestamp" in entry


def test_audit_logger_records_failure(tmp_path: Path):
    log_file = tmp_path / "test_audit.log"
    logger = AuditLogger(log_file=str(log_file))

    logger.record(
        operation="sql_dml",
        db="default",
        statements=["DELETE FROM users WHERE id = 999"],
        status="FAILED",
        rows_affected=0,
        duration_ms=5.0,
        error="模拟外键约束失败",
    )

    content = log_file.read_text(encoding="utf-8").strip()
    entry = json.loads(content)

    assert entry["status"] == "FAILED"
    assert entry["error"] == "模拟外键约束失败"


@pytest.mark.asyncio
async def test_audit_logger_async_record_with_model(tmp_path: Path):
    log_file = tmp_path / "async_audit.log"
    logger = AuditLogger(log_file=str(log_file))

    event = AuditEvent(
        operation="sql_dml",
        db="default",
        statements=["INSERT INTO logs (val) VALUES ('test')"],
        status="SUCCESS",
        rows_affected=1,
        duration_ms=3.5,
    )

    await logger.record_async(event)

    assert log_file.exists()
    line = log_file.read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    assert entry["operation"] == "sql_dml"
    assert entry["status"] == "SUCCESS"


def test_audit_logger_log_rotation(tmp_path: Path):
    """测试当单日志文件达到大小上限时的切片轮转功能."""
    log_file = tmp_path / "rot_audit.log"
    # 设置单切片大小上限为 150 字节，触发切片
    logger = AuditLogger(log_file=str(log_file), max_bytes=150, backup_count=3)

    # 写入第一条记录
    logger.record(
        operation="sql_dml",
        db="default",
        statements=["UPDATE a SET b = 1 WHERE id = 1"],
        status="SUCCESS",
    )
    assert log_file.exists()
    rot1 = log_file.with_name("rot_audit.log.1")
    assert not rot1.exists()

    # 写入第二条记录，由于超过 150 字节，应触发切片轮转
    logger.record(
        operation="sql_dml",
        db="default",
        statements=["UPDATE a SET b = 2 WHERE id = 2"],
        status="SUCCESS",
    )
    assert log_file.exists()
    assert rot1.exists()
