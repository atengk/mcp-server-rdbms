"""
mcp-server-rdbms: 数据库连接注册表与引擎生命周期管理.

@author Ateng
@since 2026-10-04
"""

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import NoSuchModuleError, SQLAlchemyError

from atengk_mcp_server_rdbms.core.dialect import DialectRegistry
from atengk_mcp_server_rdbms.core.exceptions import ConnectionNotFoundError
from atengk_mcp_server_rdbms.models.connection import ConnectionProfile

logger = logging.getLogger(__name__)


class ConnectionRegistry:
    """连接注册表：管理数据库连接配置、引擎生命周期与多库路由定位.

    @author Ateng
    @since 2026-10-04
    """

    def __init__(self, profiles: list[ConnectionProfile] | None = None) -> None:
        self._profiles: dict[str, ConnectionProfile] = {}
        self._engines: dict[str, Engine] = {}
        self._default_alias: str | None = None

        if profiles:
            for profile in profiles:
                self.register(profile)

    @property
    def default_alias(self) -> str:
        """返回当前默认连接别名."""
        return self._default_alias or "default"

    def register(self, profile: ConnectionProfile) -> None:
        """注册一个数据库连接配置.

        @param profile: 连接配置模型
        """
        self._profiles[profile.name] = profile
        if profile.is_default or self._default_alias is None:
            self._default_alias = profile.name

    def register_url(
        self,
        url: str,
        name: str = "default",
        is_default: bool = True,
        read_only: bool = False,
    ) -> ConnectionProfile:
        """通过 URL 便捷注册单个数据库连接.

        @param url: 数据库连接串
        @param name: 连接别名
        @param is_default: 是否设为默认连接
        @param read_only: 是否只读模式
        @return: 注册后的 ConnectionProfile
        """
        profile = ConnectionProfile(
            name=name,
            url=url,
            read_only=read_only,
            is_default=is_default,
        )
        self.register(profile)
        return profile

    @classmethod
    def from_file(cls, path: str | Path) -> "ConnectionRegistry":
        """从 YAML 或 JSON 配置文件加载并构建连接注册表.

        @param path: 配置文件路径
        @return: 初始化就绪的 ConnectionRegistry 实例
        @throws FileNotFoundError: 配置文件不存在时抛出
        @throws TypeError: 配置文件格式不合法时抛出
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"数据库配置文件不存在: {config_path}")

        text_content = config_path.read_text(encoding="utf-8")
        try:
            import yaml

            data = yaml.safe_load(text_content)
        except ImportError:
            import json

            data = json.loads(text_content)

        if not isinstance(data, dict):
            raise TypeError(f"配置文件顶层格式必须为映射字典，当前为: {type(data).__name__}")

        registry = cls()
        default_name = data.get("default")
        raw_conns = data.get("connections", {})

        # 支持字典格式：connections: { name: { url: ... } }
        if isinstance(raw_conns, dict):
            for name, item in raw_conns.items():
                if isinstance(item, dict) and "url" in item:
                    registry.register(cls._build_profile_from_item(name, item, default_name))
        # 支持列表格式：connections: [ { name: ..., url: ... } ]
        elif isinstance(raw_conns, list):
            for item in raw_conns:
                if isinstance(item, dict) and "name" in item and "url" in item:
                    registry.register(cls._build_profile_from_item(str(item["name"]), item, default_name))

        # 若配置文件顶层显式指定了 default，则以其为准
        if default_name and default_name in registry._profiles:
            registry._default_alias = default_name

        return registry

    @staticmethod
    def _build_profile_from_item(
        name: str,
        item: dict[str, Any],
        default_name: str | None,
    ) -> ConnectionProfile:
        """从配置项字典中抽取并构建 ConnectionProfile 实例."""
        return ConnectionProfile(
            name=name,
            url=str(item["url"]),
            read_only=bool(item.get("read_only", True)),
            is_default=(name == default_name) or bool(item.get("is_default", False)),
        )

    def _resolve_name(self, name: str | None) -> str:
        """解析目标连接别名，缺省时使用默认连接."""
        if name is None or name == "":
            return self.default_alias
        return name

    def get_profile(self, name: str | None = None) -> ConnectionProfile:
        """获取指定名称的连接配置.

        @param name: 连接别名，为 None 时获取默认连接
        @return: ConnectionProfile
        @throws ConnectionNotFoundError: 未找到对应连接
        """
        target_name = self._resolve_name(name)
        if target_name not in self._profiles:
            raise ConnectionNotFoundError(target_name)
        return self._profiles[target_name]

    def is_read_only(self, name: str | None = None) -> bool:
        """检查目标数据库连接是否处于独立只读保护状态.

        @param name: 连接别名
        @return: True 为只读保护，False 为允许修改
        """
        profile = self.get_profile(name)
        return profile.read_only

    def get_engine(self, name: str | None = None) -> Engine:
        """获取目标数据库连接的同步 SQLAlchemy 引擎（懒加载缓存模式）.

        @param name: 连接别名，为 None 时使用默认连接
        @return: Engine 实例
        @throws ConnectionNotFoundError: 未找到指定别名
        @throws DriverMissingError: 缺少数据库驱动时拦截并抛出安装指引
        """
        target_name = self._resolve_name(name)
        if target_name in self._engines:
            return self._engines[target_name]

        profile = self.get_profile(target_name)

        # 尝试创建引擎，捕获模块/驱动缺失异常并提供友好指引
        try:
            # 开启 pool_pre_ping 与 pool_recycle 确保连接健康检测与断线自愈（遵循 ADR-0006）
            engine_kwargs: dict[str, Any] = {
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
            # SQLite 内存库特殊适配避免多线程并发锁竞争
            if profile.url == "sqlite:///:memory:":
                from sqlalchemy.pool import StaticPool

                engine_kwargs["poolclass"] = StaticPool
                engine_kwargs["connect_args"] = {"check_same_thread": False}
                engine_kwargs.pop("pool_recycle", None)

            engine = create_engine(profile.url, **engine_kwargs)
            self._engines[target_name] = engine
            return engine
        except (NoSuchModuleError, ModuleNotFoundError) as exc:
            DialectRegistry.intercept(profile.url, exc)
            raise  # intercept 内部会抛出异常，此处防御保留

    def list_profiles(self) -> list[ConnectionProfile]:
        """返回全部已注册连接配置列表（无连接时返回空列表 []）.

        @return: list[ConnectionProfile]
        """
        return list(self._profiles.values())

    def close_all(self) -> None:
        """释放并关闭全部已创建的数据库引擎与连接池."""
        for engine in self._engines.values():
            try:
                engine.dispose()
            except SQLAlchemyError as exc:
                logger.warning("释放数据库引擎连接时发生异常: %s", exc)
        self._engines.clear()
