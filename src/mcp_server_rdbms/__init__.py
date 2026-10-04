"""
mcp-server-rdbms: 通用关系型数据库模型上下文协议 (MCP) 服务包.

@author Ateng
@since 2026-10-04
"""

from mcp_server_rdbms.cli import main
from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.server import create_server

__version__ = "0.1.0"
__all__ = ["ConnectionRegistry", "create_server", "main"]
