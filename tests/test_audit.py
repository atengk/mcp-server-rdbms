"""
mcp-server-rdbms: 独立审计流水记录器与日志切片轮转测试.

@author Ateng
@since 2026-10-04
"""

import json
from pathlib import Path

import pytest

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.models.audit import AuditEvent


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


def test_audit_logger_sanitizes_statements_and_error(tmp_path: Path):
    """测试审计日志中 SQL 语句字面量与 error 报错信息自动执行敏感信息脱敏净化."""
    log_file = tmp_path / "sanitize_audit.log"
    logger = AuditLogger(log_file=str(log_file))

    raw_sql = (
        "UPDATE users SET password = 'secretPassword123', secret = 'jwt_abc_token' "
        "WHERE phone = '13812345678' AND email = 'test@example.com'"
    )
    error_msg = "Constraint failed for phone 13988887777 and password 'myPlainPass'"

    logger.record(
        operation="sql_dml",
        db="default",
        statements=[raw_sql],
        status="FAILED",
        error=error_msg,
    )

    entry = json.loads(log_file.read_text(encoding="utf-8").strip())
    recorded_sql = entry["statements"][0]
    assert "secretPassword123" not in recorded_sql
    assert "jwt_abc_token" not in recorded_sql
    assert "13812345678" not in recorded_sql
    assert "test@example.com" not in recorded_sql
    assert "138****5678" in recorded_sql
    assert "t***@example.com" in recorded_sql
    assert "******" in recorded_sql

    recorded_error = entry["error"]
    assert "myPlainPass" not in recorded_error
    assert "13988887777" not in recorded_error
    assert "139****7777" in recorded_error


def test_audit_logger_masking_disabled(tmp_path: Path):
    """测试当 mask_enabled=False 时审计日志保留原始语句与错误文本."""
    log_file = tmp_path / "unmasked_audit.log"
    logger = AuditLogger(log_file=str(log_file), mask_enabled=False)

    raw_sql = "UPDATE users SET password = 'rawSecretPassword' WHERE phone = '13812345678'"
    logger.record(
        operation="sql_dml",
        db="default",
        statements=[raw_sql],
        status="SUCCESS",
    )

    entry = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert "rawSecretPassword" in entry["statements"][0]
    assert "13812345678" in entry["statements"][0]


def test_audit_logger_sanitizes_insert_statements(tmp_path: Path):
    """测试审计日志中 INSERT 语句按敏感列名位置映射净化字面量."""
    log_file = tmp_path / "insert_audit.log"
    logger = AuditLogger(log_file=str(log_file))

    raw_insert = "INSERT INTO users (id, password, phone, remark) VALUES (1, 'mySecretPwd123', '13812345678', 'normal_note')"
    logger.record(
        operation="sql_dml",
        db="default",
        statements=[raw_insert],
        status="SUCCESS",
    )

    entry = json.loads(log_file.read_text(encoding="utf-8").strip())
    recorded_sql = entry["statements"][0]
    assert "mySecretPwd123" not in recorded_sql
    assert "13812345678" not in recorded_sql
    assert "'******'" in recorded_sql
    assert "138****5678" in recorded_sql
    assert "normal_note" in recorded_sql


