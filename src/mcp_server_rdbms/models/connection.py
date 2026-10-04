"""
mcp-server-rdbms: 数据库连接配置与元数据契约定义.

@author Ateng
@since 2026-10-04
"""

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


@dataclass
class ConnectionProfile:
    """单一目标数据库连接配置声明.

    @author Ateng
    @since 2026-10-04
    """

    name: str
    url: str
    read_only: bool = True
    is_default: bool = False

    @property
    def masked_url(self) -> str:
        """返回密码强脱敏（***）后的安全连接串."""
        try:
            return make_url(self.url).render_as_string(hide_password=True)
        except (ArgumentError, ValueError):
            # 降级防御：通过正则匹配对 URL 密码部分执行强制掩码脱敏，杜绝明文凭据泄露
            import re
            if "@" in self.url and "://" in self.url:
                return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", self.url)
            return self.url

    @property
    def dialect(self) -> str:
        """返回连接所属的方言标识."""
        try:
            return make_url(self.url).get_backend_name()
        except (ArgumentError, ValueError):
            if "://" in self.url:
                scheme = self.url.split("://", 1)[0]
                return scheme.split("+", 1)[0]
            return self.url.split("+", 1)[0]


@dataclass
class ConnectionSummary:
    """已注册数据库连接脱敏清单摘要项契约.

    @author Ateng
    @since 2026-10-04
    """

    name: str
    dialect: str
    url: str
    read_only: bool
    is_default: bool

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)


@dataclass
class DatabaseInfo:
    """数据库运行环境元数据探测结果契约.

    @author Ateng
    @since 2026-10-04
    """

    database: str
    dialect: str
    driver: str
    server_version: str
    current_schema: str
    current_user: str
    connection: str = "default"

    def to_dict(self) -> dict[str, Any]:
        """转换为标准字典载荷."""
        return asdict(self)
