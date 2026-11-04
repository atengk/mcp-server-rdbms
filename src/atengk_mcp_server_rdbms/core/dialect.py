"""
mcp-server-rdbms: 方言识别与缺失驱动智能拦截注册表.

@author Ateng
@since 2026-10-04
"""

import logging
from typing import ClassVar

from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from atengk_mcp_server_rdbms.core.audit import AuditLogger, audit_logger
from atengk_mcp_server_rdbms.core.exceptions import DriverMissingError

logger = logging.getLogger(__name__)


class DialectReadOnlyAdapter:
    """跨方言只读会话适配器：在底层数据库连接执行只读约束并在不支持时优雅降级.

    @author Ateng
    @since 2026-11-04
    """

    _READONLY_COMMANDS: ClassVar[dict[str, str]] = {
        "sqlite": "PRAGMA query_only = ON",
        "postgresql": "SET TRANSACTION READ ONLY",
        "postgres": "SET TRANSACTION READ ONLY",
        "kingbase": "SET TRANSACTION READ ONLY",
        "kingbase8": "SET TRANSACTION READ ONLY",
        "mysql": "SET SESSION TRANSACTION READ ONLY",
        "mariadb": "SET SESSION TRANSACTION READ ONLY",
        "tidb": "SET SESSION TRANSACTION READ ONLY",
        "oracle": "SET TRANSACTION READ ONLY",
        "dm": "SET TRANSACTION READ ONLY",
        "clickhouse": "SET readonly = 1",
    }

    @classmethod
    def get_readonly_sql(cls, dialect: str) -> str | None:
        """根据方言名称获取原生只读会话 SQL 指令.

        @param dialect: 数据库方言标识（如 postgresql, mysql, sqlite 等）
        @return: 对应的原生只读会话指令，若无直接映射则返回 None
        """
        base_dialect = dialect.lower().split("+")[0]
        return cls._READONLY_COMMANDS.get(base_dialect)

    @classmethod
    def apply_readonly(
        cls,
        conn: Connection,
        dialect: str,
        audit: AuditLogger | None = None,
    ) -> bool:
        """在活跃数据库连接上应用只读会话声明，异常时优雅降级并记录审计流水.

        @param conn: 活跃 SQLAlchemy 数据库连接
        @param dialect: 数据库方言标识
        @param audit: 独立审计记录器实例（可选，缺省时使用全局单例）
        @return: 是否成功应用底层只读会话约束
        """
        sql = cls.get_readonly_sql(dialect)
        if not sql:
            # 未知方言尝试标准通用指令
            sql = "SET TRANSACTION READ ONLY"

        try:
            conn.execute(text(sql))
            return True
        except SQLAlchemyError as exc:
            logger.warning(
                "数据库方言 '%s' 执行只读会话声明 ('%s') 失败，已优雅降级并依赖 AST 语法守卫防御: %s",
                dialect,
                sql,
                exc,
            )
            active_audit = audit or audit_logger
            try:
                active_audit.record(
                    operation="readonly_session_fallback",
                    db=dialect,
                    statements=[sql],
                    status="FAILED",
                    error=f"只读会话声明失败降级: {exc}",
                )
            except (OSError, RuntimeError, ValueError) as audit_exc:
                logger.warning("记录只读降级审计日志时发生异常: %s", audit_exc)
            return False


class DialectRegistry:
    """方言与驱动关系注册表，负责驱动缺失检测与安装指引生成.

    @author Ateng
    @since 2026-10-04
    """

    # 已知方言及其对应的 uv 可选依赖名和驱动包名
    _KNOWN_DIALECTS: ClassVar[dict[str, dict[str, str]]] = {
        "oracle": {
            "extra": "oracle",
            "package": "oracledb",
        },
        "mssql": {
            "extra": "mssql",
            "package": "pyodbc",
        },
        "clickhouse": {
            "extra": "clickhouse",
            "package": "clickhouse-connect",
        },
        "postgresql": {
            "extra": "postgres",
            "package": "psycopg[binary]",
        },
        "postgres": {
            "extra": "postgres",
            "package": "psycopg[binary]",
        },
        "mysql": {
            "extra": "mysql",
            "package": "pymysql",
        },
        "mariadb": {
            "extra": "mysql",
            "package": "pymysql",
        },
    }

    @classmethod
    def parse_dialect_and_driver(cls, url_or_dialect: str) -> tuple[str, str | None]:
        """从连接串或方言字符串中解析方言名称与驱动名称.

        @param url_or_dialect: 数据库 URL 字符串或方言 Scheme
        @return: (dialect_name, driver_name) 二元组
        """
        if "://" in url_or_dialect:
            try:
                parsed_url = make_url(url_or_dialect)
                driver_name = parsed_url.get_driver_name()
                parts = parsed_url.drivername.split("+", 1)
                dialect_name = parts[0]
                driver = parts[1] if len(parts) > 1 else driver_name
                return dialect_name, driver
            except (ArgumentError, ValueError):
                scheme = url_or_dialect.split("://", 1)[0]
                parts = scheme.split("+", 1)
                return parts[0], parts[1] if len(parts) > 1 else None
        else:
            parts = url_or_dialect.split("+", 1)
            return parts[0], parts[1] if len(parts) > 1 else None

    @classmethod
    def get_install_hint(cls, url_or_dialect: str) -> str:
        """生成友好的缺失驱动安装指引信息.

        @param url_or_dialect: 数据库 URL 字符串或方言标识
        @return: 结构化安装提示字符串
        """
        dialect_name, driver_name = cls.parse_dialect_and_driver(url_or_dialect)
        known_info = cls._KNOWN_DIALECTS.get(dialect_name.lower())

        if known_info:
            extra = known_info["extra"]
            pkg = known_info["package"]
            return (
                f"缺少数据库驱动支持: 方言 '{dialect_name}' (驱动: '{driver_name or pkg}') 尚未安装。\n"
                f"推荐执行以下命令安装可选依赖：\n"
                f"  uv pip install \"atengk-mcp-server-rdbms[{extra}]\"\n"
                f"或者直接安装驱动包：\n"
                f"  uv pip install {pkg}\n"
                f"如果使用 uvx 运行，可通过 --with 挂载：\n"
                f"  uvx --with {pkg} atengk-mcp-server-rdbms ..."
            )

        return (
            f"缺少数据库驱动支持: 未找到方言或驱动 '{dialect_name}'。\n"
            f"如果这是自定义或专有数据库驱动，请先安装该驱动包：\n"
            f"  uv pip install <驱动包>\n"
            f"如果使用 uvx 运行，可通过 --with 挂载：\n"
            f"  uvx --with <驱动包> atengk-mcp-server-rdbms ..."
        )

    @classmethod
    def intercept(cls, url: str, exc: Exception) -> None:
        """拦截底层的模块缺失异常，直接抛出携带友好指引的 DriverMissingError.

        @param url: 数据库连接串
        @param exc: 原始异常（如 NoSuchModuleError 或 ModuleNotFoundError）
        @throws DriverMissingError: 携带结构化安装指引的自定义异常
        """
        dialect_name, driver_name = cls.parse_dialect_and_driver(url)
        hint = cls.get_install_hint(url)
        err = DriverMissingError(hint, dialect=dialect_name, driver=driver_name)
        err.__cause__ = exc
        raise err

    @classmethod
    def get_explain_prefix(cls, dialect: str) -> str:
        """根据数据库方言返回对应的 EXPLAIN 前缀语法.

        @param dialect: 数据库方言标识
        @return: 对应的 EXPLAIN 语句前缀
        """
        lower = dialect.lower()
        if lower == "sqlite":
            return "EXPLAIN QUERY PLAN"
        if lower == "oracle":
            return "EXPLAIN PLAN FOR"
        return "EXPLAIN"
