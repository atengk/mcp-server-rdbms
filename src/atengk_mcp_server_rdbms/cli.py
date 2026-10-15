"""
mcp-server-rdbms: 命令行接口解析与启动程序.

@author Ateng
@since 2026-10-04
"""

import argparse
import importlib.metadata
import platform
import sys

from mcp.server.mcpserver import MCPServer

from atengk_mcp_server_rdbms.core.audit import AuditLogger
from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.env import resolve_runtime_config
from atengk_mcp_server_rdbms.core.exceptions import DriverMissingError
from atengk_mcp_server_rdbms.models.config import ServerRuntimeConfig
from atengk_mcp_server_rdbms.server import create_server

CLI_EPILOG = """
使用示例 (Examples):
  1. 默认 stdio 模式启动（本地单库测试）：
     mcp-server-rdbms --db-url sqlite:///demo.db

  2. 启用 HTTP/SSE 模式并显式开放 DML/DDL 权限：
     mcp-server-rdbms --db-url "postgresql+psycopg://user:pass@localhost/mydb" \\
                      --transport sse --host 0.0.0.0 --port 8000 \\
                      --allow-dml --allow-ddl

  3. 多数据库连接（使用 connections.yaml 配置）：
     mcp-server-rdbms --config connections.yaml

  4. 运行环境、驱动支持矩阵与数据库连通性全面体检：
     mcp-server-rdbms --doctor
     mcp-server-rdbms --doctor --format json

  5. 使用 uvx 零安装随用随跑并挂载驱动：
     uvx --with pymysql atengk-mcp-server-rdbms --db-url "mysql+pymysql://root:pass@localhost/db"

专属环境变量速查表 (Dedicated Environment Variables):
  MCP_RDBMS_DB_URL             默认单数据库连接串
  MCP_RDBMS_DB_<ALIAS>         声明多数据库别名连接（如 MCP_RDBMS_DB_ANALYTICS）
  MCP_RDBMS_DBS                逗号分隔聚合声明多数据库连接（如 crm=url1,erp=url2）
  MCP_RDBMS_DEFAULT_DB         多库模式下的默认数据库别名
  MCP_RDBMS_ALLOW_DML          开启数据修改 (DML) 权限 (true/false)
  MCP_RDBMS_ALLOW_DDL          开启结构变更 (DDL) 权限 (true/false)
  MCP_RDBMS_TRANSPORT          通信协议 (stdio / sse / streamable-http)
  MCP_RDBMS_SERVER_HOST        HTTP/SSE 监听地址 (默认 127.0.0.1)
  MCP_RDBMS_SERVER_PORT        HTTP/SSE 监听端口 (默认 8000)
  MCP_RDBMS_AUTH_TOKEN         HTTP/SSE 模式下的 Bearer 访问令牌认证门禁
  MCP_RDBMS_ALLOWED_HOSTS      HTTP/SSE 模式下的 Host 主机白名单 (逗号分隔或 '*' 通配全部)
  MCP_RDBMS_ALLOWED_ORIGINS    HTTP/SSE 模式下的 Origin 来源白名单 (逗号分隔或 '*' 通配全部)
  MCP_RDBMS_CORS_ORIGINS       跨域资源共享 (CORS) 允许来源列表 (逗号分隔或 '*' 通配全部)
  MCP_RDBMS_AUDIT_LOG_FILE     审计日志路径 (默认 rdbms_mcp_audit.log)
  MCP_RDBMS_AUDIT_MODE         审计范围 (mutation / all / off)
  MCP_RDBMS_SERVER_NAME        自定义服务实例显示名称（多服务独立挂载时区分业务）
  MCP_RDBMS_SERVER_INSTRUCTIONS 面向大模型的专属业务提示词指令

可选驱动一键安装指引 (Dialect Drivers):
  内置驱动支持: SQLite, PostgreSQL (psycopg3), MySQL (pymysql)
  Oracle:       uv pip install "atengk-mcp-server-rdbms[oracle]"
  SQL Server:   uv pip install "atengk-mcp-server-rdbms[mssql]"
  ClickHouse:   uv pip install "atengk-mcp-server-rdbms[clickhouse]"
  全量可选依赖: uv pip install "atengk-mcp-server-rdbms[all]"
"""


def get_version_string() -> str:
    """获取格式化的服务版本与运行时运行环境信息.

    @return: 格式化版本信息字符串
    """
    try:
        ver = importlib.metadata.version("atengk-mcp-server-rdbms")
    except importlib.metadata.PackageNotFoundError:
        ver = "0.0.0.dev0"

    try:
        sa_ver = importlib.metadata.version("sqlalchemy")
    except importlib.metadata.PackageNotFoundError:
        sa_ver = "未知"

    py_ver = f"{platform.python_version()} ({platform.python_implementation()})"
    plat = f"{platform.system()} {platform.machine()}"
    return f"atengk-mcp-server-rdbms v{ver} (Python {py_ver}, SQLAlchemy {sa_ver} on {plat})"


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """解析命令行启动参数.

    @param args: 参数列表，为 None 时读取 sys.argv[1:]
    @return: 解析后的 Namespace 对象
    """
    parser = argparse.ArgumentParser(
        prog="mcp-server-rdbms",
        description="通用关系型数据库模型上下文协议 (MCP) 服务 (Universal Relational Database MCP Server)",
        epilog=CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=get_version_string(),
        help="显示服务版本及运行时运行环境信息并退出",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        default=False,
        help="执行运行环境、数据库驱动矩阵、环境变量合规性与连接连通性全方位自检诊断探针",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="配合 --doctor 使用的输出格式（text 终端富文本卡片, json 机器可读格式）",
    )
    parser.add_argument(
        "--server-name",
        type=str,
        default=None,
        help="自定义 MCP 服务实例显示名称（默认: mcp-server-rdbms，支持环境变量 MCP_RDBMS_SERVER_NAME）",
    )
    parser.add_argument(
        "--server-instructions",
        type=str,
        default=None,
        help="面向大模型注入的专属业务系统指令（支持环境变量 MCP_RDBMS_SERVER_INSTRUCTIONS）",
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
        "--auth-token",
        type=str,
        default=None,
        help="远端 HTTP/SSE 模式下的访问令牌认证门禁（支持环境变量 MCP_RDBMS_AUTH_TOKEN）",
    )
    parser.add_argument(
        "--allowed-hosts",
        type=str,
        default=None,
        help="HTTP/SSE 允许访问的主机 Host 白名单（逗号分隔或 '*' 通配全部，支持环境变量 MCP_RDBMS_ALLOWED_HOSTS）",
    )
    parser.add_argument(
        "--allowed-origins",
        type=str,
        default=None,
        help="HTTP/SSE 允许访问的来源 Origin 白名单（逗号分隔或 '*' 通配全部，支持环境变量 MCP_RDBMS_ALLOWED_ORIGINS）",
    )
    parser.add_argument(
        "--cors-origins",
        type=str,
        default=None,
        help="跨域资源共享 (CORS) 允许来源列表（逗号分隔或 '*' 通配全部，支持环境变量 MCP_RDBMS_CORS_ORIGINS）",
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


def run_http_server(
    server: MCPServer,
    transport: str,
    host: str,
    port: int,
    auth_token: str | None = None,
    allowed_hosts: tuple[str, ...] | list[str] | None = None,
    allowed_origins: tuple[str, ...] | list[str] | None = None,
    cors_origins: tuple[str, ...] | list[str] | None = None,
) -> None:
    """启动并运行 HTTP 传输层服务（支持可选 Bearer Token 门禁、CORS 与 Uvicorn 调度）.

    @param server: 已装配领域工具的 MCPServer 实例
    @param transport: 通信协议（sse 或 streamable-http）
    @param host: 监听主机地址
    @param port: 监听端口号
    @param auth_token: 可选访问令牌，设置后强制校验请求凭据
    @param allowed_hosts: 允许的主机 Host 白名单（支持 '*' 通配）
    @param allowed_origins: 允许的来源 Origin 白名单（支持 '*' 通配）
    @param cors_origins: 允许跨域资源共享的 Origin 列表（支持 '*' 通配）
    """
    import anyio
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    # 1. 构建底层传输层安全设置（DNS Rebinding 防御配置）
    transport_security: TransportSecuritySettings | None = None
    if allowed_hosts or allowed_origins:
        effective_hosts = list(allowed_hosts or [])
        effective_origins = list(allowed_origins or [])

        # 若包含全局通配符 '*'，则直接关闭 DNS Rebinding 保护（适用于受信任私网或前置网关场景）
        if "*" in effective_hosts or "*" in effective_origins:
            transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            )
        else:
            default_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
            default_origins = [
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
            ]
            all_hosts = set(default_hosts)
            all_origins = set(default_origins)
            for h in effective_hosts:
                all_hosts.add(h)
                if not h.endswith(":*"):
                    all_hosts.add(f"{h}:*")
            for o in effective_origins:
                all_origins.add(o)
                if not o.endswith(":*"):
                    all_origins.add(f"{o}:*")

            transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=sorted(all_hosts),
                allowed_origins=sorted(all_origins),
            )

    # 2. 构造 Starlette 应用实例
    if transport == "sse":
        app = server.sse_app(host=host, transport_security=transport_security)
    elif transport == "streamable-http":
        app = server.streamable_http_app(host=host, transport_security=transport_security)
    else:
        raise ValueError(f"不支持的 HTTP 传输协议: {transport}")

    # 3. 挂载访问令牌认证中间件（内层）
    if auth_token:
        from atengk_mcp_server_rdbms.core.auth import TokenAuthMiddleware

        app.add_middleware(TokenAuthMiddleware, token=auth_token)

    # 4. 挂载跨域 CORS 中间件（外层，确保未授权 401 响应亦携带 CORS 头）
    if cors_origins:
        from starlette.middleware.cors import CORSMiddleware

        cors_list = list(cors_origins)
        allow_all = "*" in cors_list
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"] if allow_all else cors_list,
            allow_credentials=not allow_all,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=server.settings.log_level.lower(),
    )
    uv_server = uvicorn.Server(config)
    anyio.run(uv_server.serve)


def main(args: list[str] | None = None) -> None:
    """主程序启动入口.

    @param args: 命令行参数，缺省时读取终端参数
    """
    parsed = parse_args(args)

    # 1. 处理 --doctor 自检探针
    if parsed.doctor:
        from atengk_mcp_server_rdbms.core.doctor import (
            DoctorDiagnostic,
            render_doctor_console,
        )

        cfg = resolve_runtime_config(args=parsed)
        registry = build_registry(cfg)
        try:
            diag = DoctorDiagnostic(config=cfg, registry=registry)
            report = diag.diagnose()
            if parsed.format == "json":
                sys.stdout.write(report.to_json(indent=2) + "\n")
            else:
                render_doctor_console(report)
            sys.exit(report.exit_code)
        finally:
            registry.close_all()

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
        name=cfg.server_name,
        instructions=cfg.server_instructions,
    )

    try:
        if cfg.transport == "stdio":
            server.run(transport="stdio")
        elif cfg.transport in {"sse", "streamable-http"}:
            run_http_server(
                server,
                transport=cfg.transport,
                host=cfg.host,
                port=cfg.port,
                auth_token=cfg.auth_token,
                allowed_hosts=cfg.allowed_hosts,
                allowed_origins=cfg.allowed_origins,
                cors_origins=cfg.cors_origins,
            )
    except KeyboardInterrupt:
        sys.stderr.write("\n服务已由用户主动终止。\n")
    finally:
        registry.close_all()


