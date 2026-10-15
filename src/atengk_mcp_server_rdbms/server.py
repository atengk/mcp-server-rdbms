"""
mcp-server-rdbms: FastMCP 服务装配与生命周期协调器.

@author Ateng
@since 2026-10-04
"""

from mcp.server.mcpserver import MCPServer

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.resources.provider import register_resources
from atengk_mcp_server_rdbms.tools.db_info import register_db_info_tool
from atengk_mcp_server_rdbms.tools.schema_info import register_schema_tools
from atengk_mcp_server_rdbms.tools.sql_ddl import register_ddl_tools
from atengk_mcp_server_rdbms.tools.sql_dml import register_dml_tools
from atengk_mcp_server_rdbms.tools.sql_query import register_query_tools

DEFAULT_INSTRUCTIONS: str = (
    "通用关系型数据库 MCP 服务，提供只读探查与受控操作。"
    "支持多数据库路由，可通过 rdbms://connections 资源或 db_info 工具查看已配置连接清单；"
    "在多数据库环境下，请在调用工具时显式传入 db 参数指定目标数据库连接别名。"
)


def create_server(
    registry: ConnectionRegistry | None = None,
    allow_dml: bool = False,
    allow_ddl: bool = False,
    audit: AuditLogger | None = None,
    name: str = "mcp-server-rdbms",
    instructions: str | None = None,
) -> MCPServer:
    """创建并装配 FastMCP 服务实例.

    @param registry: 数据库连接注册表，若为空则创建新实例
    @param allow_dml: 是否激活 DML 数据修改操作（默认 False 保护）
    @param allow_ddl: 是否激活 DDL 结构定义操作（默认 False 保护）
    @param audit: 独立审计记录器实例
    @param name: 服务名称（支持通过 --server-name 或 MCP_RDBMS_SERVER_NAME 定制）
    @param instructions: 面向大模型的系统指令（支持通过 --server-instructions 或 MCP_RDBMS_SERVER_INSTRUCTIONS 定制）
    @return: 已装配领域工具的 MCPServer 实例
    """
    if registry is None:
        registry = ConnectionRegistry()

    server = MCPServer(
        name=name,
        instructions=instructions or DEFAULT_INSTRUCTIONS,
    )

    # 1. 装配 db_ 命名空间核心探测工具 (db_info)
    register_db_info_tool(server, registry)

    # 2. 装配 schema_ 命名空间表与结构全息探查工具 (schema_list_tables, schema_describe_table)
    register_schema_tools(server, registry)

    # 3. 装配 sql_ 命名空间只读查询与分析工具 (sql_query，含 explain 模式)
    register_query_tools(server, registry, audit=audit)

    # 4. 装配 sql_ 命名空间 DML 变更工具（受 allow_dml 门禁控制）(sql_dml)
    register_dml_tools(server, registry, allow_dml=allow_dml, audit=audit)

    # 5. 装配 sql_ 命名空间 DDL 结构变更工具（受 allow_ddl 门禁控制）(sql_ddl)
    register_ddl_tools(server, registry, allow_ddl=allow_ddl, audit=audit)

    # 6. 装配 MCP 只读模式资源暴露器 (rdbms://connections, rdbms://{db}/schema, rdbms://audit/recent)
    register_resources(server, registry, audit=audit)

    # 7. 装配通用健康检查与就绪探活路由 (/health, /ping)
    register_health_endpoints(server)

    return server


def register_health_endpoints(server: MCPServer) -> None:
    """注册通用存活与健康检查探针路由（免认证公开路由，供容器编排与反代探活）.

    @param server: FastMCP 服务实例
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    @server.custom_route("/health", methods=["GET"])
    async def health_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": server.name})

    @server.custom_route("/ping", methods=["GET"])
    async def ping_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "pong"})

