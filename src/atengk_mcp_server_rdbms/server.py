"""
mcp-server-rdbms: FastMCP 服务装配与生命周期协调器.

@author Ateng
@since 2026-10-04
"""

from mcp.server.mcpserver import MCPServer

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.tools.admin_queries import register_admin_tools
from atengk_mcp_server_rdbms.tools.db_info import register_db_info_tool
from atengk_mcp_server_rdbms.tools.schema_info import register_schema_tools
from atengk_mcp_server_rdbms.tools.sql_ddl import register_ddl_tools
from atengk_mcp_server_rdbms.tools.sql_dml import register_dml_tools
from atengk_mcp_server_rdbms.tools.sql_query import register_query_tools


def create_server(
    registry: ConnectionRegistry | None = None,
    allow_dml: bool = False,
    allow_ddl: bool = False,
    audit: AuditLogger | None = None,
    name: str = "mcp-server-rdbms",
) -> MCPServer:
    """创建并装配 FastMCP 服务实例.

    @param registry: 数据库连接注册表，若为空则创建新实例
    @param allow_dml: 是否激活 DML 数据修改操作（默认 False 保护）
    @param allow_ddl: 是否激活 DDL 结构定义操作（默认 False 保护）
    @param audit: 独立审计记录器实例
    @param name: 服务名称
    @return: 已装配领域工具的 MCPServer 实例
    """
    if registry is None:
        registry = ConnectionRegistry()

    server = MCPServer(
        name=name,
        instructions="通用关系型数据库 MCP 服务，提供只读探查与受控操作。",
    )

    # 1. 装配 db_ 命名空间核心探测工具
    register_db_info_tool(server, registry)

    # 2. 装配 schema_ 命名空间表与结构全息探查工具
    register_schema_tools(server, registry)

    # 3. 装配 sql_ 命名空间只读查询与分析工具
    register_query_tools(server, registry)

    # 4. 装配 sql_ 命名空间 DML 变更工具（受 allow_dml 门禁控制）
    register_dml_tools(server, registry, allow_dml=allow_dml, audit=audit)

    # 5. 装配 sql_ 命名空间 DDL 结构变更工具（受 allow_ddl 门禁控制）
    register_ddl_tools(server, registry, allow_ddl=allow_ddl, audit=audit)

    # 6. 装配 admin_ 命名空间运维观测工具
    register_admin_tools(server, registry)

    return server
