"""
mcp-server-rdbms: 通用关系型数据库模型上下文协议 (MCP) 服务包.

@author Ateng
@since 2026-10-04
"""

from importlib.metadata import PackageNotFoundError, version

from atengk_mcp_server_rdbms.cli import main
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.server import create_server

try:
    __version__ = version("atengk-mcp-server-rdbms")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = ["ConnectionRegistry", "__version__", "create_server", "main"]
