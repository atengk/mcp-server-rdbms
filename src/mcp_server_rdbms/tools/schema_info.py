"""
mcp-server-rdbms: 数据库模式探查、表清单与全息表结构工具.

@author Ateng
@since 2026-10-04
"""

import logging
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import inspect
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError

from mcp_server_rdbms.core.connection import ConnectionRegistry
from mcp_server_rdbms.core.exceptions import (
    ConnectionNotFoundError,
    DriverMissingError,
    TableNotFoundError,
)
from mcp_server_rdbms.core.schema_filter import SchemaFilter
from mcp_server_rdbms.models.schema import (
    ColumnDetail,
    ForeignKeyTopology,
    IndexDetail,
    TableDetail,
    TableListResult,
    TableSummary,
)

logger = logging.getLogger(__name__)


def _get_table_comment(inspector: Inspector, table_name: str, schema: str | None) -> str | None:
    """安全读取数据表或视图注释文本，出错时静默降级并记录调试日志.

    @param inspector: SQLAlchemy 反射检查器
    @param table_name: 数据表或视图名称
    @param schema: 目标模式
    @return: 注释文本或 None
    """
    try:
        comment_dict = inspector.get_table_comment(table_name, schema=schema)
        return comment_dict.get("text") if comment_dict else None
    except (SQLAlchemyError, NotImplementedError) as exc:
        logger.debug("获取目标 %s 注释失败: %s", table_name, exc)
        return None


def _convert_foreign_key(fk_dict: dict[str, Any], constrained_table: str) -> ForeignKeyTopology:
    """将 SQLAlchemy 反射外键字典转换为领域 ForeignKeyTopology 模型.

    @param fk_dict: SQLAlchemy 反射外键属性字典
    @param constrained_table: 外键所属源表名
    @return: ForeignKeyTopology 模型实例
    """
    return ForeignKeyTopology(
        constrained_table=constrained_table,
        constrained_columns=fk_dict.get("constrained_columns", []) or [],
        referred_table=str(fk_dict.get("referred_table") or ""),
        referred_columns=fk_dict.get("referred_columns", []) or [],
        referred_schema=fk_dict.get("referred_schema"),
        name=fk_dict.get("name"),
    )


def fetch_tables_summary(
    registry: ConnectionRegistry,
    schema: str | None,
    include_views: bool,
    db: str | None,
) -> dict[str, Any]:
    """同步获取数据表/视图清单及全库外键拓扑关系（在工作线程池执行）.

    @param registry: 数据库连接注册表
    @param schema: 目标模式名称（可选）
    @param include_views: 是否包含视图
    @param db: 数据库连接别名（可选）
    @return: 包含 tables 与 foreign_keys 的字典载荷
    """
    engine = registry.get_engine(db)
    inspector = inspect(engine)
    dialect_name = engine.dialect.name

    target_schema = schema or inspector.default_schema_name
    if target_schema is None:
        # 未选定默认数据库（例如直接连接 MySQL 实例未指定库名）
        try:
            available_schemas = [
                s for s in inspector.get_schema_names()
                if not SchemaFilter.is_system_schema(s)
            ]
            if available_schemas:
                target_schema = available_schemas[0]
            else:
                # 实例无业务数据库或全为保留库，安全返回空集合
                return TableListResult(schema=None, tables=[], foreign_keys=[]).to_dict()
        except (SQLAlchemyError, AttributeError, NotImplementedError) as exc:
            logger.debug("探测可用 schema 失败: %s", exc)
            return TableListResult(schema=None, tables=[], foreign_keys=[]).to_dict()

    # 1. 模式合法性校验与系统模式安全拦截
    if SchemaFilter.is_system_schema(target_schema):
        return TableListResult(schema=target_schema, tables=[], foreign_keys=[]).to_dict()

    # 2. 获取并过滤业务数据表列表
    try:
        raw_tables = inspector.get_table_names(schema=target_schema)
    except (SQLAlchemyError, AttributeError, NotImplementedError) as exc:
        logger.debug("获取表名列表降级: %s", exc)
        raw_tables = []
    tables = SchemaFilter.filter_tables(raw_tables, dialect=dialect_name)

    tables_list: list[TableSummary] = []
    for tbl in tables:
        comment = _get_table_comment(inspector, tbl, schema=target_schema)
        tables_list.append(TableSummary(name=tbl, type="table", comment=comment))

    # 3. 按需探测视图清单
    if include_views:
        try:
            raw_views = inspector.get_view_names(schema=target_schema)
            views = SchemaFilter.filter_tables(raw_views, dialect=dialect_name)
            for view_name in views:
                view_comment = _get_table_comment(inspector, view_name, schema=target_schema)
                tables_list.append(TableSummary(name=view_name, type="view", comment=view_comment))
        except (SQLAlchemyError, AttributeError, NotImplementedError) as exc:
            logger.debug("获取视图清单失败: %s", exc)

    # 4. 聚合数据表间外键约束拓扑关系
    fk_list: list[ForeignKeyTopology] = []
    for tbl in tables:
        try:
            fks = inspector.get_foreign_keys(tbl, schema=target_schema)
            for fk in fks:
                fk_list.append(_convert_foreign_key(fk, tbl))
        except (SQLAlchemyError, AttributeError, NotImplementedError) as exc:
            logger.debug("获取表 %s 外键拓扑失败: %s", tbl, exc)

    return TableListResult(schema=target_schema, tables=tables_list, foreign_keys=fk_list).to_dict()


def fetch_table_detail(
    registry: ConnectionRegistry,
    table_name: str,
    schema: str | None,
    db: str | None,
) -> dict[str, Any]:
    """同步获取指定表的列明细、主键、外键与索引列表（在工作线程池执行）.

    @param registry: 数据库连接注册表
    @param table_name: 数据表名称
    @param schema: 目标模式名称（可选）
    @param db: 数据库连接别名（可选）
    @return: TableDetail 字典载荷
    @throws TableNotFoundError: 数据表不存在
    """
    if SchemaFilter.is_system_schema(schema):
        raise TableNotFoundError(table_name, schema)

    engine = registry.get_engine(db)
    inspector = inspect(engine)
    dialect_name = engine.dialect.name

    lookup_schema = schema
    if lookup_schema is None and dialect_name == "mysql" and inspector.default_schema_name is None:
        try:
            available_schemas = [
                s for s in inspector.get_schema_names()
                if not SchemaFilter.is_system_schema(s)
            ]
            if available_schemas:
                lookup_schema = available_schemas[0]
            else:
                raise TableNotFoundError(table_name, schema)
        except (SQLAlchemyError, AttributeError, NotImplementedError):
            raise TableNotFoundError(table_name, schema)

    # 1. 验证目标表或视图是否存在（排除系统保留表）
    try:
        raw_tables = inspector.get_table_names(schema=lookup_schema)
    except (SQLAlchemyError, AttributeError, NotImplementedError) as exc:
        logger.debug("获取表名列表失败: %s", exc)
        raw_tables = []
    all_tables = SchemaFilter.filter_tables(raw_tables, dialect=dialect_name)
    all_views: list[str] = []
    try:
        raw_views = inspector.get_view_names(schema=lookup_schema)
        all_views = SchemaFilter.filter_tables(raw_views, dialect=dialect_name)
    except (SQLAlchemyError, NotImplementedError) as exc:
        logger.debug("获取视图名称失败: %s", exc)

    if table_name not in all_tables and table_name not in all_views:
        raise TableNotFoundError(table_name, schema)

    # 2. 提取主键约束列
    pk_cols: list[str] = []
    try:
        pk = inspector.get_pk_constraint(table_name, schema=lookup_schema)
        pk_cols = pk.get("constrained_columns", []) or []
    except (SQLAlchemyError, NotImplementedError) as exc:
        logger.debug("获取表 %s 主键约束失败: %s", table_name, exc)

    # 3. 提取列字段定义明细
    col_details: list[ColumnDetail] = []
    try:
        cols = inspector.get_columns(table_name, schema=lookup_schema)
        for col in cols:
            is_pk = bool(col.get("primary_key", False)) or (col["name"] in pk_cols)
            col_details.append(
                ColumnDetail(
                    name=col["name"],
                    type=str(col["type"]),
                    nullable=bool(col.get("nullable", True)),
                    default=str(col["default"]) if col.get("default") is not None else None,
                    primary_key=is_pk,
                    comment=col.get("comment"),
                )
            )
    except (SQLAlchemyError, NotImplementedError) as exc:
        logger.debug("获取表 %s 列明细失败: %s", table_name, exc)

    # 4. 提取外键约束明细
    fk_details: list[ForeignKeyTopology] = []
    try:
        fks = inspector.get_foreign_keys(table_name, schema=lookup_schema)
        for fk in fks:
            fk_details.append(_convert_foreign_key(fk, table_name))
    except (SQLAlchemyError, NotImplementedError) as exc:
        logger.debug("获取表 %s 外键约束失败: %s", table_name, exc)

    # 5. 提取索引明细
    idx_details: list[IndexDetail] = []
    try:
        idxs = inspector.get_indexes(table_name, schema=lookup_schema)
        for idx in idxs:
            idx_details.append(
                IndexDetail(
                    name=idx["name"],
                    columns=idx.get("column_names", []) or [],
                    unique=bool(idx.get("unique", False)),
                )
            )
    except (SQLAlchemyError, NotImplementedError) as exc:
        logger.debug("获取表 %s 索引明细失败: %s", table_name, exc)

    # 6. 读取数据表注释
    table_comment = _get_table_comment(inspector, table_name, schema=lookup_schema)

    return TableDetail(
        table_name=table_name,
        schema=lookup_schema,
        columns=col_details,
        primary_key=pk_cols,
        foreign_keys=fk_details,
        indexes=idx_details,
        comment=table_comment,
    ).to_dict()


def register_schema_tools(server: MCPServer, registry: ConnectionRegistry) -> None:
    """向 FastMCP 服务注册 schema_ 命名空间核心探查工具.

    @param server: FastMCP 服务实例
    @param registry: 数据库连接注册表
    """

    @server.tool(
        name="schema_list_tables",
        description="获取指定模式下的数据表/视图清单、表注释以及全库外键拓扑关系。",
    )
    async def schema_list_tables(
        schema: str | None = None,
        include_views: bool = False,
        db: str | None = None,
    ) -> dict[str, Any]:
        """获取数据表清单与外键拓扑关系.

        @param schema: 目标 Schema 模式名称，缺省时探测默认模式
        @param include_views: 是否包含视图，默认 False
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 tables 与 foreign_keys 的结果字典
        """
        try:
            return await anyio.to_thread.run_sync(
                fetch_tables_summary, registry, schema, include_views, db
            )
        except (DriverMissingError, ConnectionNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise ToolError(f"获取数据表清单失败: {exc}") from exc

    @server.tool(
        name="schema_describe_table",
        description="一站式获取指定数据表的列定义明细（类型、可空性、默认值）、主键约束、外键约束与全部索引。",
    )
    async def schema_describe_table(
        table_name: str,
        schema: str | None = None,
        db: str | None = None,
    ) -> dict[str, Any]:
        """一站式全息探查数据表结构.

        @param table_name: 待探查的数据表名
        @param schema: 目标 Schema 模式名称，缺省时探测默认模式
        @param db: 目标数据库连接别名，缺省时使用默认连接
        @return: 包含 columns、primary_key、foreign_keys、indexes 的结果字典
        """
        try:
            return await anyio.to_thread.run_sync(
                fetch_table_detail, registry, table_name, schema, db
            )
        except (TableNotFoundError, DriverMissingError, ConnectionNotFoundError) as exc:
            raise ToolError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise ToolError(f"获取数据表结构失败: {exc}") from exc
