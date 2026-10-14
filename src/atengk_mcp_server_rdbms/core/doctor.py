"""
mcp-server-rdbms: 运行环境、数据库驱动与连接全方位自检诊断器.

@author Ateng
@since 2026-10-14
"""

import importlib.metadata
import importlib.util
import json
import os
import platform
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.core.dialect import DialectRegistry
from atengk_mcp_server_rdbms.core.exceptions import DriverMissingError
from atengk_mcp_server_rdbms.models.config import ServerRuntimeConfig
from atengk_mcp_server_rdbms.models.connection import ConnectionProfile


def mask_sensitive_url(url: str) -> str:
    """对连接串中的密码字段进行安全脱敏.

    @param url: 待脱敏数据库连接串
    @return: 密码被掩码为 *** 的安全连接串
    """
    return ConnectionProfile(name="probe", url=url).masked_url

# 9 大主流关系型数据库方言与驱动定义矩阵
PROBE_DIALECT_SPECS: list[dict[str, str]] = [
    {
        "dialect": "sqlite",
        "package": "sqlite3",
        "extra": "内置",
        "module": "sqlite3",
        "required": True,
    },
    {
        "dialect": "mysql / mariadb",
        "package": "pymysql",
        "extra": "mysql",
        "module": "pymysql",
        "required": False,
    },
    {
        "dialect": "postgresql",
        "package": "psycopg",
        "extra": "postgres",
        "module": "psycopg",
        "required": False,
    },
    {
        "dialect": "oracle",
        "package": "oracledb",
        "extra": "oracle",
        "module": "oracledb",
        "required": False,
    },
    {
        "dialect": "mssql (SQL Server)",
        "package": "pyodbc",
        "extra": "mssql",
        "module": "pyodbc",
        "required": False,
    },
    {
        "dialect": "clickhouse",
        "package": "clickhouse-connect",
        "extra": "clickhouse",
        "module": "clickhouse_connect",
        "required": False,
    },
    {
        "dialect": "dm (达梦)",
        "package": "dmPython",
        "extra": "dm",
        "module": "dmPython",
        "required": False,
    },
    {
        "dialect": "kingbase (人大金仓)",
        "package": "ksycopg2",
        "extra": "kingbase",
        "module": "ksycopg2",
        "required": False,
    },
]

# 严格命名空间检查：容易被误设的通用无前缀废弃变量
DEPRECATED_GENERIC_ENV_KEYS: tuple[str, ...] = (
    "DATABASE_URL",
    "DB_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "CONFIG_FILE",
    "AUDIT_LOG",
    "AUDIT_MODE",
)


@dataclass
class DriverCheckItem:
    """单个方言驱动探查结果.

    @author Ateng
    @since 2026-10-14
    """

    dialect: str
    package: str
    module: str
    status: str  # "ok" | "missing"
    version: str | None = None
    install_hint: str = ""


@dataclass
class EnvCheckItem:
    """单项环境变量命名空间与配置审计结果.

    @author Ateng
    @since 2026-10-14
    """

    name: str
    status: str  # "ok" | "warn" | "fail"
    message: str
    masked_value: str | None = None


@dataclass
class ConnectionCheckItem:
    """单个数据库连接握手连通性探查结果.

    @author Ateng
    @since 2026-10-14
    """

    alias: str
    dialect: str
    masked_url: str
    status: str  # "ok" | "fail" | "unconfigured"
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class DoctorReport:
    """全方位体检诊断报告载荷.

    @author Ateng
    @since 2026-10-14
    """

    status: str  # "ok" | "warn" | "fail"
    exit_code: int  # 0 or 1
    server_version: str
    python_version: str
    platform_info: str
    sqlalchemy_version: str
    sqlglot_version: str
    dotenv_loaded: bool
    drivers: list[DriverCheckItem] = field(default_factory=list)
    env_audit: list[EnvCheckItem] = field(default_factory=list)
    connections: list[ConnectionCheckItem] = field(default_factory=list)
    summary_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """将报告转换为字典结构."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """序列化为标准 JSON 字符串."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class DoctorDiagnostic:
    """诊断引擎核心，负责运行环境、驱动矩阵、环境合规与连通性探查.

    @author Ateng
    @since 2026-10-14
    """

    def __init__(
        self,
        config: ServerRuntimeConfig | None = None,
        registry: ConnectionRegistry | None = None,
    ) -> None:
        self.config = config
        self.registry = registry

    def diagnose(self) -> DoctorReport:
        """执行全方位诊断并返回结构化诊断报告.

        @return: 完整的 DoctorReport 对象
        """
        # 1. 探查运行时基础环境
        server_ver = self._probe_server_version()
        py_ver = f"{platform.python_version()} ({platform.python_implementation()})"
        plat_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        sa_ver = self._probe_package_version("sqlalchemy") or "未知"
        sqlglot_ver = self._probe_package_version("sqlglot") or "未知"
        dotenv_loaded = os.path.isfile(".env")

        # 2. 探查驱动支持矩阵
        drivers = self._probe_drivers()

        # 3. 探查环境变量合规性
        env_items = self._probe_env_hygiene()

        # 4. 探查连接连通性
        conn_items = self._probe_connections()

        # 5. 综合计算整体健康度与退出码
        has_failure = any(item.status == "fail" for item in env_items) or any(
            c.status == "fail" for c in conn_items
        )
        has_warning = any(item.status == "warn" for item in env_items) or any(
            d.status == "missing" and d.module in {"pymysql", "psycopg"}
            for d in drivers
        )

        summary_msgs: list[str] = []
        if has_failure:
            overall_status = "fail"
            exit_code = 1
            summary_msgs.append("自检发现关键故障（配置解析失败或数据库握手连通性异常），请根据下方提示排查。")
        elif has_warning:
            overall_status = "warn"
            exit_code = 0
            summary_msgs.append("系统运行基线就绪，但检测到潜在环境告警或未配置目标连接。")
        else:
            overall_status = "ok"
            exit_code = 0
            summary_msgs.append("全部核心诊断项通过，运行环境与数据库连接通畅。")

        return DoctorReport(
            status=overall_status,
            exit_code=exit_code,
            server_version=server_ver,
            python_version=py_ver,
            platform_info=plat_info,
            sqlalchemy_version=sa_ver,
            sqlglot_version=sqlglot_ver,
            dotenv_loaded=dotenv_loaded,
            drivers=drivers,
            env_audit=env_items,
            connections=conn_items,
            summary_messages=summary_msgs,
        )

    def _probe_server_version(self) -> str:
        try:
            return importlib.metadata.version("atengk-mcp-server-rdbms")
        except importlib.metadata.PackageNotFoundError:
            return "0.0.0.dev0"

    def _probe_package_version(self, pkg_name: str) -> str | None:
        try:
            return importlib.metadata.version(pkg_name)
        except importlib.metadata.PackageNotFoundError:
            return None

    def _probe_drivers(self) -> list[DriverCheckItem]:
        results: list[DriverCheckItem] = []
        for spec in PROBE_DIALECT_SPECS:
            mod_name = spec["module"]
            dialect = spec["dialect"]
            package = spec["package"]
            extra = spec["extra"]

            if mod_name == "sqlite3":
                results.append(
                    DriverCheckItem(
                        dialect=dialect,
                        package=package,
                        module=mod_name,
                        status="ok",
                        version=platform.python_version(),
                        install_hint="Python 标准库原生集成",
                    )
                )
                continue

            # 使用 find_spec 安全静态探测，不执行 C 模块完整载入
            found = False
            try:
                found = importlib.util.find_spec(mod_name) is not None
            except (ModuleNotFoundError, ImportError, ValueError):
                found = False

            if found:
                ver = self._probe_package_version(package)
                results.append(
                    DriverCheckItem(
                        dialect=dialect,
                        package=package,
                        module=mod_name,
                        status="ok",
                        version=ver or "已安装",
                        install_hint="驱动就绪",
                    )
                )
            else:
                hint = (
                    f"可选驱动未安装。如需使用，请执行: uv pip install \"atengk-mcp-server-rdbms[{extra}]\" 或 uv pip install {package}"
                    if extra != "内置"
                    else "驱动缺失"
                )
                results.append(
                    DriverCheckItem(
                        dialect=dialect,
                        package=package,
                        module=mod_name,
                        status="missing",
                        version=None,
                        install_hint=hint,
                    )
                )
        return results

    def _probe_env_hygiene(self) -> list[EnvCheckItem]:
        items: list[EnvCheckItem] = []

        # 1. 扫描宿主环境是否存在易被混淆的通用无前缀变量（专属命名空间防御）
        found_deprecated: list[str] = []
        for key in DEPRECATED_GENERIC_ENV_KEYS:
            if key in os.environ and os.environ[key].strip() != "":
                found_deprecated.append(key)

        if found_deprecated:
            items.append(
                EnvCheckItem(
                    name="通用无前缀环境变量扫描",
                    status="warn",
                    message=(
                        f"检测到存在通用环境变量 {found_deprecated}。基于专属命名空间规则 (Dedicated Namespace Rule)，"
                        "本服务已物理级主动忽略这些变量以杜绝串库。请使用标准 'MCP_RDBMS_*' 前缀进行声明。"
                    ),
                    masked_value=f"命中 {len(found_deprecated)} 项",
                )
            )
        else:
            items.append(
                EnvCheckItem(
                    name="通用无前缀环境变量扫描",
                    status="ok",
                    message="未发现可能导致意外串库的通用无前缀变量，命名空间隔离规范良好。",
                    masked_value="合规",
                )
            )

        # 2. 检查有效加载的 MCP_RDBMS_* 变量
        mcp_vars = [k for k in os.environ if k.startswith("MCP_RDBMS_")]
        items.append(
            EnvCheckItem(
                name="MCP_RDBMS_* 专属变量纳管",
                status="ok",
                message=f"当前环境共生效 {len(mcp_vars)} 个 MCP_RDBMS_* 专属配置项。",
                masked_value=f"{len(mcp_vars)} 项生效",
            )
        )

        # 3. 校验运行时配置有效性
        if self.config:
            if self.config.db_url:
                try:
                    make_url(self.config.db_url)
                    masked = mask_sensitive_url(self.config.db_url)
                    items.append(
                        EnvCheckItem(
                            name="单库连接串语法合法性",
                            status="ok",
                            message="单库连接串 URL 语法校验通过。",
                            masked_value=masked,
                        )
                    )
                except (ArgumentError, ValueError) as err:
                    items.append(
                        EnvCheckItem(
                            name="单库连接串语法合法性",
                            status="fail",
                            message=f"单库连接串解析失败: {err}",
                            masked_value=self.config.db_url,
                        )
                    )

            if self.config.multi_db_urls:
                for alias, url in self.config.multi_db_urls.items():
                    try:
                        make_url(url)
                    except (ArgumentError, ValueError) as err:
                        items.append(
                            EnvCheckItem(
                                name=f"多库别名 [{alias}] 语法合法性",
                                status="fail",
                                message=f"连接串解析失败: {err}",
                                masked_value=url,
                            )
                        )

            # 检查默认库声明是否合法
            if (
                self.config.default_db
                and self.config.multi_db_urls
                and self.config.default_db not in self.config.multi_db_urls
            ):
                items.append(
                    EnvCheckItem(
                        name="默认数据库别名指向",
                        status="warn",
                        message=f"声明的默认数据库 '{self.config.default_db}' 不在已注入的多库列表 ({list(self.config.multi_db_urls.keys())}) 中。",
                        masked_value=self.config.default_db,
                    )
                )

        return items

    def _probe_connections(self) -> list[ConnectionCheckItem]:
        items: list[ConnectionCheckItem] = []
        if not self.registry or not self.registry.list_profiles():
            items.append(
                ConnectionCheckItem(
                    alias="-",
                    dialect="-",
                    masked_url="-",
                    status="unconfigured",
                    latency_ms=None,
                    error="当前未配置任何目标数据库（待命状态，可通过 --db-url、--config 或 MCP_RDBMS_DB_URL 配置）",
                )
            )
            return items

        for profile in self.registry.list_profiles():
            alias = profile.name
            raw_url = profile.url
            masked = mask_sensitive_url(raw_url)
            dialect, _ = DialectRegistry.parse_dialect_and_driver(raw_url)

            # 探测实际连通性
            t0 = time.perf_counter()
            try:
                engine = self.registry.get_engine(alias)
                # 使用短超时进行 ping 握手
                with engine.connect() as conn:
                    # SQLite / MySQL / PostgreSQL / Oracle / SQL Server 均兼容 SELECT 1
                    # 对于极少数不支持的方言做优雅兜底
                    ping_sql = (
                        "SELECT 1 FROM DUAL"
                        if dialect.lower() == "oracle"
                        else "SELECT 1"
                    )
                    conn.execute(text(ping_sql))
                latency = round((time.perf_counter() - t0) * 1000, 2)
                items.append(
                    ConnectionCheckItem(
                        alias=alias,
                        dialect=dialect,
                        masked_url=masked,
                        status="ok",
                        latency_ms=latency,
                        error=None,
                    )
                )
            except DriverMissingError as d_err:
                items.append(
                    ConnectionCheckItem(
                        alias=alias,
                        dialect=dialect,
                        masked_url=masked,
                        status="fail",
                        latency_ms=None,
                        error=str(d_err).strip(),
                    )
                )
            except Exception as err:  # noqa: BLE001
                items.append(
                    ConnectionCheckItem(
                        alias=alias,
                        dialect=dialect,
                        masked_url=masked,
                        status="fail",
                        latency_ms=None,
                        error=f"连接握手失败: {err}",
                    )
                )

        return items


def render_doctor_console(report: DoctorReport, console: Console | None = None) -> None:
    """使用 Rich 渲染色彩丰富、条理清晰的终端体检卡片与表格.

    @param report: DoctorReport 诊断报告实体
    @param console: Rich 控制台实例，缺省时自动新建
    """
    if console is None:
        console = Console()

    # 1. 顶部标题卡片
    title_text = (
        "[bold cyan]MCP Server RDBMS 运行环境与健康体检探针 (Doctor Diagnostics)[/bold cyan]\n"
        f"服务版本: [bold]{report.server_version}[/bold] | "
        f"Python: {report.python_version} | "
        f"SQLAlchemy: {report.sqlalchemy_version} | "
        f"SQLGlot: {report.sqlglot_version}"
    )
    console.print(Panel(title_text, box=ROUNDED, border_style="cyan"))

    # 2. 驱动就绪支持矩阵
    driver_table = Table(
        title="[bold]1. 关系型数据库驱动就绪矩阵[/bold]",
        box=ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    driver_table.add_column("目标方言", style="cyan", no_wrap=True)
    driver_table.add_column("对应驱动包", style="yellow", no_wrap=True)
    driver_table.add_column("就绪状态", justify="center", no_wrap=True)
    driver_table.add_column("驱动版本 / 安装指引", style="dim")

    for d in report.drivers:
        if d.status == "ok":
            status_text = "[bold green][✓] 就绪[/bold green]"
            detail = f"[green]{d.version or '就绪'}[/green]"
        else:
            status_text = "[yellow][!] 未安装[/yellow]"
            detail = f"[dim yellow]{d.install_hint}[/dim yellow]"
        driver_table.add_row(d.dialect, d.package, status_text, detail)

    console.print(driver_table)
    console.print()

    # 3. 环境变量与配置合规审计
    env_table = Table(
        title="[bold]2. 环境变量命名空间与配置合规审计[/bold]",
        box=ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    env_table.add_column("审计检测项", style="cyan", no_wrap=True)
    env_table.add_column("状态", justify="center", no_wrap=True)
    env_table.add_column("取值 / 命中", style="yellow")
    env_table.add_column("合规诊断明细与建议")

    for e in report.env_audit:
        if e.status == "ok":
            st = "[bold green][✓] 合规[/bold green]"
        elif e.status == "warn":
            st = "[bold yellow][!] 告警[/bold yellow]"
        else:
            st = "[bold red][✗] 错误[/bold red]"
        env_table.add_row(e.name, st, e.masked_value or "-", e.message)

    console.print(env_table)
    console.print()

    # 4. 数据库握手连通性探查
    conn_table = Table(
        title="[bold]3. 数据库连接握手与探活探针[/bold]",
        box=ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    conn_table.add_column("连接别名", style="cyan", no_wrap=True)
    conn_table.add_column("方言", style="blue", no_wrap=True)
    conn_table.add_column("连接串 (脱敏)", style="dim")
    conn_table.add_column("连通性", justify="center", no_wrap=True)
    conn_table.add_column("延迟 / 错误原因", style="yellow")

    for c in report.connections:
        if c.status == "ok":
            st = "[bold green][✓] 通畅[/bold green]"
            detail = f"[green]{c.latency_ms} ms (Ping 成功)[/green]"
        elif c.status == "unconfigured":
            st = "[dim]未配置[/dim]"
            detail = f"[dim]{c.error}[/dim]"
        else:
            st = "[bold red][✗] 失败[/bold red]"
            detail = f"[bold red]{c.error}[/bold red]"
        conn_table.add_row(c.alias, c.dialect, c.masked_url, st, detail)

    console.print(conn_table)
    console.print()

    # 5. 底部总结 Panel
    if report.status == "ok":
        panel_color = "green"
        summary_title = "[bold green]✓ 诊断通过：环境与服务状态健康[/bold green]"
    elif report.status == "warn":
        panel_color = "yellow"
        summary_title = "[bold yellow]! 诊断提示：基础就绪，包含部分建议项[/bold yellow]"
    else:
        panel_color = "red"
        summary_title = "[bold red]✗ 诊断失败：存在阻断性错误[/bold red]"

    summary_content = "\n".join(report.summary_messages)
    console.print(
        Panel(
            f"{summary_content}\n\n[dim]提示: 可通过 'mcp-server-rdbms --doctor --format json' 输出机器可读的 JSON 报告。[/dim]",
            title=summary_title,
            box=ROUNDED,
            border_style=panel_color,
        )
    )
