"""
mcp-server-rdbms: 环境变量分层解析与连接串自动拼装器.

@author Ateng
@since 2026-10-04
"""

import argparse
import os
import urllib.parse
from collections.abc import Mapping

from atengk_mcp_server_rdbms.models.config import ServerRuntimeConfig

# 推荐方言与核心驱动映射表（与 dialect.py 保持同步）
DEFAULT_DIALECT_DRIVERS: dict[str, str] = {
    "mysql": "mysql+pymysql",
    "postgres": "postgresql+psycopg",
    "postgresql": "postgresql+psycopg",
    "oracle": "oracle+oracledb",
    "mssql": "mssql+pyodbc",
    "sqlserver": "mssql+pyodbc",
    "sqlite": "sqlite",
    "dm": "dm+dmPython",
    "kingbase": "kingbase8+ksycopg2",
}

# 默认端口映射表
DEFAULT_DIALECT_PORTS: dict[str, int] = {
    "mysql": 3306,
    "postgresql": 5432,
    "postgres": 5432,
    "oracle": 1521,
    "mssql": 1433,
    "sqlserver": 1433,
    "dm": 5236,
    "kingbase": 54321,
}

TRUE_BOOLEAN_STRINGS: frozenset[str] = frozenset({"1", "true", "yes", "on", "t"})


def load_dotenv_if_exists(dotenv_path: str = ".env") -> dict[str, str]:
    """自适应加载本地 .env 文件（轻量零第三方依赖）.

    遵循安全防御原则：仅在系统环境中不存在同名键时注入，不覆盖既有环境变量。

    @param dotenv_path: .env 相对或绝对路径，默认当前工作目录下的 .env
    @return: 成功从文件中解析并载入的键值字典
    """
    loaded: dict[str, str] = {}
    if not os.path.isfile(dotenv_path):
        return loaded

    try:
        with open(dotenv_path, encoding="utf-8") as f:
            for line in f:
                raw_line = line.strip()
                if not raw_line or raw_line.startswith("#"):
                    continue
                if "=" not in raw_line:
                    continue
                key, _, val = raw_line.partition("=")
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = val
                    loaded[key] = val
    except (OSError, UnicodeDecodeError):
        return loaded

    return loaded


def parse_bool_env(value: str | None) -> bool:
    """宽容布尔值转换器.

    支持 1, true, yes, on, t（不区分大小写与首尾空格）解析为 True.

    @param value: 环境变量原始字符串
    @return: 解析后的布尔值
    """
    if not value:
        return False
    return value.strip().lower() in TRUE_BOOLEAN_STRINGS


def get_first_env(keys: list[str], env: Mapping[str, str] | None = None) -> str | None:
    """按优先级顺序获取首个非空环境变量.

    @param keys: 环境变量候选键名列表
    @param env: 环境变量映射源，缺省时使用 os.environ
    @return: 命中且非空的值，若均未命中返回 None
    """
    source = os.environ if env is None else env
    for key in keys:
        val = source.get(key)
        if val is not None and val.strip() != "":
            return val.strip()
    return None


def assemble_db_url_from_env(env: Mapping[str, str] | None = None) -> str | None:
    """环境自动拼装器：从环境变量自动组合数据库连接串.

    优先级与规则：
    1. 完整连接串：优先 MCP_RDBMS_DB_URL，兼容 DATABASE_URL。
    2. 原子字段拼装：当提供了方言、主机、端口、用户名、密码或库名等任意明确线索时触发组合。
       针对密码中的特殊字符（@, #, :, /, 空格等）自动执行 RFC 1738 安全转义（空格转为 %20），避免手动编码。

    @param env: 环境变量映射源，缺省时使用 os.environ
    @return: 组合完成的 RFC 1738 连接串，若无任何相关配置返回 None
    """
    source = os.environ if env is None else env

    # 1. 优先提取完整 URL
    full_url = get_first_env(["MCP_RDBMS_DB_URL", "DATABASE_URL"], env=source)
    if full_url:
        return full_url

    # 2. 提取原子字段（严格隔离数据库字段与服务监听字段）
    dialect_raw = get_first_env(["MCP_RDBMS_DIALECT", "DB_DIALECT"], env=source)
    host = get_first_env(["MCP_RDBMS_DB_HOST", "DB_HOST"], env=source)
    port_str = get_first_env(["MCP_RDBMS_DB_PORT", "DB_PORT"], env=source)
    user = get_first_env(["MCP_RDBMS_USER", "DB_USER", "DB_USERNAME"], env=source)
    password = get_first_env(["MCP_RDBMS_PASSWORD", "DB_PASSWORD", "DB_PASS"], env=source)
    database = get_first_env(["MCP_RDBMS_DATABASE", "DB_NAME", "DB_DATABASE"], env=source)
    params = get_first_env(["MCP_RDBMS_PARAMS", "DB_PARAMS"], env=source)

    # 若没有任何字段线索，直接返回 None
    if not any([dialect_raw, host, port_str, user, password, database]):
        return None

    # 规范化方言与驱动
    dialect_clean = dialect_raw.strip().lower() if dialect_raw else ""
    if not dialect_clean:
        # 若未指定方言，若端口为 5432 则推导为 postgresql，否则默认 mysql
        if port_str == "5432":
            dialect_clean = "postgresql"
        else:
            dialect_clean = "mysql"

    driver = DEFAULT_DIALECT_DRIVERS.get(dialect_clean, dialect_raw if dialect_raw else "mysql+pymysql")

    # SQLite 特殊处理
    if dialect_clean == "sqlite" or driver.startswith("sqlite"):
        if not database or database == ":memory:":
            return "sqlite:///:memory:"
        return f"sqlite:///{database}"

    # 处理主机与端口
    target_host = host or "127.0.0.1"
    if port_str:
        try:
            target_port = int(port_str)
        except ValueError:
            target_port = DEFAULT_DIALECT_PORTS.get(dialect_clean, 3306)
    else:
        target_port = DEFAULT_DIALECT_PORTS.get(dialect_clean, 3306)

    # 处理认证授权（核心：特殊字符安全 URL 编码防御，使用 quote 将空格安全转为 %20）
    auth_part = ""
    safe_password: str | None = None
    if password is not None:
        raw_password = urllib.parse.unquote(password)
        safe_password = urllib.parse.quote(raw_password, safe="")

    if user and safe_password is not None:
        auth_part = f"{user}:{safe_password}@"
    elif user:
        auth_part = f"{user}@"
    elif safe_password is not None:
        auth_part = f":{safe_password}@"

    db_part = database or ""
    query_part = f"?{params}" if params else ""

    return f"{driver}://{auth_part}{target_host}:{target_port}/{db_part}{query_part}"


def resolve_runtime_config(
    args: argparse.Namespace | None = None,
    env: Mapping[str, str] | None = None,
) -> ServerRuntimeConfig:
    """分层解析服务器全量运行时配置.

    优先级契约：命令行参数 > 环境变量 > 默认规范值.

    @param args: 命令行参数对象，若为 None 则全部由环境变量/默认值推导
    @param env: 环境变量映射源，缺省时使用 os.environ
    @return: 解析完成的 ServerRuntimeConfig 实体
    """
    if env is None:
        load_dotenv_if_exists()

    source = os.environ if env is None else env

    arg_config = getattr(args, "config", None) if args else None
    arg_db_url = getattr(args, "db_url", None) if args else None
    arg_allow_dml = bool(getattr(args, "allow_dml", False)) if args else False
    arg_allow_ddl = bool(getattr(args, "allow_ddl", False)) if args else False
    arg_transport = getattr(args, "transport", None) if args else None
    arg_host = getattr(args, "host", None) if args else None
    arg_port = getattr(args, "port", None) if args else None

    config_file = arg_config or get_first_env(["MCP_RDBMS_CONFIG", "CONFIG_FILE"], env=source)
    db_url = arg_db_url or assemble_db_url_from_env(env=source)

    allow_dml = arg_allow_dml or parse_bool_env(
        get_first_env(["MCP_RDBMS_ALLOW_DML", "MCP_ALLOW_DML"], env=source)
    )
    allow_ddl = arg_allow_ddl or parse_bool_env(
        get_first_env(["MCP_RDBMS_ALLOW_DDL", "MCP_ALLOW_DDL"], env=source)
    )

    transport = (
        arg_transport
        or get_first_env(["MCP_RDBMS_TRANSPORT", "MCP_TRANSPORT"], env=source)
        or "stdio"
    )

    host = (
        arg_host
        or get_first_env(["MCP_RDBMS_SERVER_HOST", "HOST"], env=source)
        or "127.0.0.1"
    )

    port_env_str = get_first_env(["MCP_RDBMS_SERVER_PORT", "PORT"], env=source)
    if arg_port is not None:
        port = arg_port
    elif port_env_str:
        try:
            port = int(port_env_str)
        except ValueError:
            port = 8000
    else:
        port = 8000

    return ServerRuntimeConfig(
        config_file=config_file,
        db_url=db_url,
        allow_dml=allow_dml,
        allow_ddl=allow_ddl,
        transport=transport,
        host=host,
        port=port,
    )
