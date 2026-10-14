"""
mcp-server-rdbms: 服务器运行时配置数据契约模型.

@author Ateng
@since 2026-10-04
"""

from typing import NamedTuple


class ServerRuntimeConfig(NamedTuple):
    """服务器运行时解析配置载荷.

    @author Ateng
    @since 2026-10-04
    """

    config_file: str | None
    db_url: str | None
    allow_dml: bool
    allow_ddl: bool
    transport: str
    host: str
    port: int
    multi_db_urls: dict[str, str] | None = None
    default_db: str | None = None
    audit_log_file: str = "rdbms_mcp_audit.log"
    audit_mode: str = "mutation"
    audit_max_bytes: int = 10 * 1024 * 1024
    audit_backup_count: int = 5
