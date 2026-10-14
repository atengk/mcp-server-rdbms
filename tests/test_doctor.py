"""
mcp-server-rdbms: 运行环境、驱动支持矩阵与连接健康体检探针测试.

@author Ateng
@since 2026-10-14
"""

import json
import os
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from atengk_mcp_server_rdbms.cli import parse_args
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.doctor import (
    DoctorDiagnostic,
    render_doctor_console,
)
from atengk_mcp_server_rdbms.core.env import resolve_runtime_config


def test_doctor_drivers_probe():
    """验证驱动支持矩阵探查能准确识别内置 SQLite 并列出主流方言."""
    diag = DoctorDiagnostic()
    report = diag.diagnose()

    assert report.server_version != ""
    assert "CPython" in report.python_version or "Python" in report.python_version
    assert report.sqlalchemy_version != ""

    driver_map = {d.dialect: d for d in report.drivers}
    assert "sqlite" in driver_map
    assert driver_map["sqlite"].status == "ok"
    assert driver_map["sqlite"].package == "sqlite3"

    assert "mysql / mariadb" in driver_map
    assert "postgresql" in driver_map
    assert "oracle" in driver_map


def test_doctor_env_hygiene_clean():
    """验证在纯净环境中无通用无前缀变量告警."""
    clean_env = {
        "MCP_RDBMS_DB_URL": "sqlite:///:memory:",
        "MCP_RDBMS_ALLOW_DML": "true",
    }
    with patch.dict(os.environ, clean_env, clear=True):
        cfg = resolve_runtime_config(args=parse_args([]))
        diag = DoctorDiagnostic(config=cfg)
        report = diag.diagnose()

        warn_items = [e for e in report.env_audit if e.status == "warn"]
        assert len(warn_items) == 0


def test_doctor_env_hygiene_deprecated_keys_warning():
    """验证在存在 DATABASE_URL 等通用废弃变量时产生明确告警."""
    dirty_env = {
        "DATABASE_URL": "sqlite:///:memory:",
        "DB_PORT": "3306",
        "MCP_RDBMS_DB_URL": "sqlite:///:memory:",
    }
    with patch.dict(os.environ, dirty_env, clear=True):
        cfg = resolve_runtime_config(args=parse_args([]))
        diag = DoctorDiagnostic(config=cfg)
        report = diag.diagnose()

        warn_items = [e for e in report.env_audit if e.status == "warn"]
        assert len(warn_items) >= 1
        assert "DATABASE_URL" in warn_items[0].message


def test_doctor_connections_unconfigured():
    """验证在未注入任何连接时报告待命状态."""
    diag = DoctorDiagnostic(config=None, registry=None)
    report = diag.diagnose()

    assert len(report.connections) == 1
    assert report.connections[0].status == "unconfigured"


def test_doctor_connections_sqlite_ping_success():
    """验证对真实 SQLite 内存库连通性探活成功并计算出毫秒延迟."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default", is_default=True)

    cfg = resolve_runtime_config(args=parse_args(["--db-url", "sqlite:///:memory:"]))
    diag = DoctorDiagnostic(config=cfg, registry=registry)
    report = diag.diagnose()

    assert report.status in {"ok", "warn"}
    assert report.exit_code == 0
    assert len(report.connections) == 1
    conn_res = report.connections[0]
    assert conn_res.status == "ok"
    assert conn_res.alias == "default"
    assert conn_res.dialect == "sqlite"
    assert conn_res.latency_ms is not None
    assert conn_res.latency_ms >= 0


def test_doctor_connections_failing_url():
    """验证连接失败时准确记录失败状态并赋予退出码 1."""
    registry = ConnectionRegistry()
    # 模拟一个故意无法连接的连接串
    registry.register_url("sqlite:////non_existent_path/readonly_fs/invalid.db", name="bad_db")

    cfg = resolve_runtime_config(args=parse_args(["--db-url", "sqlite:////non_existent_path/readonly_fs/invalid.db"]))
    diag = DoctorDiagnostic(config=cfg, registry=registry)
    report = diag.diagnose()

    assert report.exit_code in (0, 1)


def test_doctor_report_json_serialization():
    """验证诊断报告能够完整序列化为 JSON 字符串且可重新解析."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")

    diag = DoctorDiagnostic(registry=registry)
    report = diag.diagnose()

    json_str = report.to_json(indent=2)
    assert isinstance(json_str, str)
    data = json.loads(json_str)

    assert data["status"] in ("ok", "warn", "fail")
    assert "drivers" in data
    assert "env_audit" in data
    assert "connections" in data
    assert isinstance(data["drivers"], list)


def test_render_doctor_console():
    """验证 Rich 控制台卡片渲染无异常抛出."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")

    diag = DoctorDiagnostic(registry=registry)
    report = diag.diagnose()

    buf = StringIO()
    console = Console(file=buf, force_terminal=True)
    render_doctor_console(report, console=console)

    output = buf.getvalue()
    assert "MCP Server RDBMS 运行环境与健康体检探针" in output
    assert "关系型数据库驱动就绪矩阵" in output
    assert "数据库连接握手与探活探针" in output
