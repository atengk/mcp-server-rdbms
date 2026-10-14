"""
mcp-server-rdbms: MCP 只读模式资源暴露器 (Schema Resource Provider).

@author Ateng
@since 2026-10-14
"""

import json
import logging

import anyio
from mcp.server.mcpserver import MCPServer
from sqlalchemy.exc import SQLAlchemyError

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
)
from atengk_mcp_server_rdbms.models.connection import ConnectionSummary
from atengk_mcp_server_rdbms.tools.schema_info import fetch_tables_summary

logger = logging.getLogger(__name__)


def register_resources(server: MCPServer, registry: ConnectionRegistry) -> None:
    """向 FastMCP 服务注册只读 MCP Resources 协议支持.

    1. 挂载 rdbms://connections 静态资源：暴露当前全量连接清单与状态；
    2. 挂载 rdbms://{db}/schema 动态资源模板：暴露指定数据库的表清单与注释概要。

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    """

    @server.resource(
        "rdbms://connections",
        name="connections",
        title="数据库连接清单",
        description="获取所有已配置数据库连接别名、方言、默认库标记与只读状态",
        mime_type="application/json",
    )
    async def get_connections_resource() -> str:
        """获取当前所有已配置数据库连接的只读脱敏清单资源."""
        profiles = registry.list_profiles()
        connections = [
            ConnectionSummary(
                name=p.name,
                dialect=p.dialect,
                url=p.masked_url,
                read_only=p.read_only,
                is_default=(p.name == registry.default_alias),
            ).to_dict()
            for p in profiles
        ]

        payload = {
            "default_connection": registry.default_alias if profiles else None,
            "total": len(connections),
            "connections": connections,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @server.resource(
        "rdbms://{db}/schema",
        name="db_schema",
        title="数据库模式与表清单",
        description="获取指定数据库连接的模式名称、业务表清单与表注释概要",
        mime_type="application/json",
    )
    async def get_db_schema_resource(db: str) -> str:
        """获取目标数据库的模式与业务表清单概要资源（支持容灾降级）."""
        try:
            # 同步 I/O 严格通过 anyio.to_thread.run_sync 异步卸载至工作线程池（遵循 Core Invariant 1）
            data = await anyio.to_thread.run_sync(
                fetch_tables_summary,
                registry,
                None,   # schema (None 表示自动解析默认 schema)
                True,   # include_views
                False,  # include_foreign_keys (默认 False 避免 N+1 瓶颈)
                None,   # pattern (不过滤)
                db,     # 目标数据库连接别名
            )
            payload = {
                "db": db,
                "status": "connected",
                "schema": data.get("schema"),
                "total_tables": len(data.get("tables", [])),
                "tables": data.get("tables", []),
            }
        except (ConnectionNotFoundError, DriverMissingError) as exc:
            payload = {
                "db": db,
                "status": "error",
                "error": str(exc),
                "schema": None,
                "total_tables": 0,
                "tables": [],
            }
        except SQLAlchemyError as exc:
            logger.warning("获取数据库 %s 模式资源失败: %s", db, exc)
            payload = {
                "db": db,
                "status": "error",
                "error": f"数据库连接不可达或探查失败: {exc}",
                "schema": None,
                "total_tables": 0,
                "tables": [],
            }

        return json.dumps(payload, ensure_ascii=False, indent=2)
