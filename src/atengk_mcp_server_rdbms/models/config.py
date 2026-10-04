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
