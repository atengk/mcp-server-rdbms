"""
mcp-server-rdbms: 命令行接口解析与启动程序.

@author Ateng
@since 2026-10-04
"""

import argparse
import sys

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.env import resolve_runtime_config
from atengk_mcp_server_rdbms.core.exceptions import DriverMissingError
from atengk_mcp_server_rdbms.models.config import ServerRuntimeConfig
from atengk_mcp_server_rdbms.server import create_server


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """解析命令行启动参数.

    @param args: 参数列表，为 None 时读取 sys.argv[1:]
    @return: 解析后的 Namespace 对象
    """
    parser = argparse.ArgumentParser(
        prog="mcp-server-rdbms",
        description="通用关系型数据库模型上下文协议 (MCP) 服务",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="单数据库连接串（例如: sqlite:///test.db 或 postgresql://user:pass@host/db）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="多数据库配置文件路径（connections.yaml）",
    )
    parser.add_argument(
        "--allow-dml",
        action="store_true",
        default=False,
        help="显式允许执行增删改 DML 操作（默认禁用）",
    )
    parser.add_argument(
        "--allow-ddl",
        action="store_true",
        default=False,
        help="显式允许执行结构定义 DDL 操作（默认禁用）",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="服务通信传输协议（默认: stdio，支持环境变量 MCP_RDBMS_TRANSPORT）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="HTTP/SSE 监听主机地址（默认: 127.0.0.1，支持环境变量 MCP_RDBMS_SERVER_HOST）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP/SSE 监听端口（默认: 8000，支持环境变量 MCP_RDBMS_SERVER_PORT）",
    )
    parser.add_argument(
        "--audit-log",
        type=str,
        default=None,
        help="审计日志输出文件路径（默认: rdbms_mcp_audit.log，支持环境变量 MCP_RDBMS_AUDIT_LOG_FILE）",
    )
    parser.add_argument(
        "--audit-mode",
        type=str,
        choices=["mutation", "all", "off"],
        default=None,
        help="审计记录范围模式（默认: mutation 仅变更, all 全量含只读查询, off 关闭）",
    )
    parser.add_argument(
        "--audit-max-bytes",
        type=int,
        default=None,
        help="单文件触发切片轮转的最大字节数（默认: 10485760 字节/10MB）",
    )
    parser.add_argument(
        "--audit-backup-count",
        type=int,
        default=None,
        help="审计日志保留的历史切片副本数（默认: 5）",
    )

    return parser.parse_args(args)


def build_registry(cfg: ServerRuntimeConfig) -> ConnectionRegistry:
    """根据运行时解析配置构建连接注册表.

    优先级与规则：
    1. 配置文件优先：若指定 config_file，从文件加载全量配置；
    2. 环境变量多库优先：若存在 multi_db_urls，动态批量注册并设置 default_db；
    3. 单连接兜底：若存在 db_url，注册为 default 连接。

    @param cfg: 服务器运行时配置实体
    @return: 初始化就绪的 ConnectionRegistry
    """
    if cfg.config_file:
        return ConnectionRegistry.from_file(cfg.config_file)

    registry = ConnectionRegistry()

    # 1. 优先加载环境变量注入的多数据库配置 (MCP_RDBMS_DB_<ALIAS>)
    if cfg.multi_db_urls:
        for alias, url in cfg.multi_db_urls.items():
            is_default = (alias == cfg.default_db)
            registry.register_url(url, name=alias, is_default=is_default)

        # 若显式指定了 default_db 且在注册列表中，锁定为默认
        if cfg.default_db and cfg.default_db in registry._profiles:
            registry._default_alias = cfg.default_db
        elif "default" in registry._profiles:
            registry._default_alias = "default"
        elif registry._profiles and registry._default_alias is None:
            registry._default_alias = next(iter(registry._profiles.keys()))

    # 2. 单连接配置（兼容 MCP_RDBMS_DB_URL 与原子字段拼装）
    elif cfg.db_url:
        registry.register_url(cfg.db_url, name="default", is_default=True)

    return registry


def build_registry_from_args(args: argparse.Namespace) -> ConnectionRegistry:
    """根据命令行参数与环境变量构建连接注册表（向后兼容包装函数）.

    @param args: 命令行参数对象
    @return: 初始化就绪的 ConnectionRegistry
    """
    cfg = resolve_runtime_config(args=args)
    return build_registry(cfg)


def main(args: list[str] | None = None) -> None:
    """主程序启动入口.

    @param args: 命令行参数，缺省时读取终端参数
    """
    parsed = parse_args(args)
    cfg = resolve_runtime_config(args=parsed)
    registry = build_registry(cfg)

    # 若配置了数据库连接，预先探测默认库驱动可用性
    if registry.list_profiles():
        try:
            registry.get_engine()
        except DriverMissingError as exc:
            sys.stderr.write(f"\n[启动失败] {exc}\n\n")
            sys.exit(1)

    audit = AuditLogger(
        log_file=cfg.audit_log_file,
        mode=cfg.audit_mode,
        max_bytes=cfg.audit_max_bytes,
        backup_count=cfg.audit_backup_count,
    )

    server = create_server(
        registry,
        allow_dml=cfg.allow_dml,
        allow_ddl=cfg.allow_ddl,
        audit=audit,
    )

    try:
        if cfg.transport == "stdio":
            server.run(transport="stdio")
        elif cfg.transport == "sse":
            server.run(transport="sse", host=cfg.host, port=cfg.port)
        elif cfg.transport == "streamable-http":
            server.run(transport="streamable-http", host=cfg.host, port=cfg.port)
    except KeyboardInterrupt:
        sys.stderr.write("\n服务已由用户主动终止。\n")
        registry.close_all()
