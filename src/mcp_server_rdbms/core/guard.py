"""
mcp-server-rdbms: 基于 sqlglot 的 AST 语法树安全分析与 LIMIT 注入守卫.

@author Ateng
@since 2026-10-04
"""

from typing import ClassVar

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from mcp_server_rdbms.core.exceptions import SecurityViolationError


class ASTGuard:
    """AST 语法树安全守卫：只读性验证、防多语句拼接、自动 LIMIT 注入与 DML 条件防护.

    @author Ateng
    @since 2026-10-04
    """

    # 严禁在只读查询中出现的写入与破坏性 AST 节点类型（包含 SELECT INTO 等伪只读语句）
    _FORBIDDEN_MUTATION_NODES: ClassVar[tuple[type[exp.Expression], ...]] = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Merge,
        exp.Command,
        exp.Transaction,
        exp.Into,
    )

    # 允许作为顶层只读查询的 AST 节点类型
    _ALLOWED_QUERY_ROOTS: ClassVar[tuple[type[exp.Expression], ...]] = (
        exp.Select,
        exp.Union,
        exp.Intersect,
        exp.Except,
    )

    # 方言别名映射：解决 SQLAlchemy 方言名与 sqlglot 方言名的命名差异
    _DIALECT_MAP: ClassVar[dict[str, str]] = {
        "postgresql": "postgres",
        "mssql": "tsql",
    }

    # 允许作为 DML 数据操作的顶层 AST 节点类型（仅严格限定增删改）
    _ALLOWED_DML_ROOTS: ClassVar[tuple[type[exp.Expression], ...]] = (
        exp.Insert,
        exp.Update,
        exp.Delete,
    )

    # 严禁在 DML 数据操作中出现的 DDL 与控制节点类型
    _FORBIDDEN_DML_NODES: ClassVar[tuple[type[exp.Expression], ...]] = (
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Command,
        exp.Transaction,
    )

    # 允许作为 DDL 结构定义变更的顶层 AST 节点类型
    _ALLOWED_DDL_ROOTS: ClassVar[tuple[type[exp.Expression], ...]] = (
        exp.Create,
        exp.Alter,
        exp.Drop,
        exp.TruncateTable,
    )

    @classmethod
    def _normalize_dialect(cls, dialect: str | None) -> str | None:
        """归一化方言名称至 sqlglot 兼容标识."""
        if not dialect:
            return None
        return cls._DIALECT_MAP.get(dialect.lower(), dialect.lower())

    @classmethod
    def _parse_and_validate_ast(
        cls,
        sql: str,
        dialect: str | None = None,
    ) -> exp.Expression:
        """内部方法：执行语法树解析、多语句拦截与纯只读性深度校验.

        @param sql: 原始 SQL 文本
        @param dialect: 数据库方言标识（可选）
        @return: 校验合规的 AST 根表达式节点
        @throws SecurityViolationError: 违规时抛出
        """
        stripped = sql.strip().rstrip(";")
        if not stripped:
            raise SecurityViolationError("SQL 查询语句不能为空。")

        norm_dialect = cls._normalize_dialect(dialect)
        try:
            expressions = sqlglot.parse(sql, read=norm_dialect)
        except ParseError as exc:
            raise SecurityViolationError(f"SQL 语法树解析失败: {exc}") from exc

        valid_expressions = [e for e in expressions if e is not None]
        if not valid_expressions:
            raise SecurityViolationError("SQL 语句未能解析为有效语法树。")

        if len(valid_expressions) > 1:
            raise SecurityViolationError("为防止注入风险，严禁拼接执行多条 SQL 语句。")

        expr = valid_expressions[0]

        for node in expr.walk():
            if isinstance(node, cls._FORBIDDEN_MUTATION_NODES):
                raise SecurityViolationError(
                    f"只读查询中禁止包含修改或结构定义操作（检测到非法节点: {type(node).__name__}）。"
                )

        if not isinstance(expr, cls._ALLOWED_QUERY_ROOTS):
            raise SecurityViolationError(
                f"当前操作不是支持的只读查询语句（检测到语句类型: {type(expr).__name__}）。"
            )

        return expr

    @classmethod
    def validate_read_only(
        cls,
        sql: str,
        dialect: str | None = None,
    ) -> str:
        """纯只读性验证（不追加 LIMIT，供 EXPLAIN 执行计划分析使用）.

        @param sql: 待校验的原始 SQL 文本
        @param dialect: 数据库方言标识（可选）
        @return: 经校验安全的原始 SQL 文本
        @throws SecurityViolationError: 包含写入操作、多语句拼接或语法错误时抛出
        """
        expr = cls._parse_and_validate_ast(sql, dialect=dialect)
        norm_dialect = cls._normalize_dialect(dialect)
        return expr.sql(dialect=norm_dialect)

    @classmethod
    def validate_and_rewrite_query(
        cls,
        sql: str,
        limit: int = 100,
        dialect: str | None = None,
    ) -> str:
        """校验 SQL 查询的只读安全性，并在缺省时注入 LIMIT 截断限制.

        @param sql: 待校验的原始 SQL 文本
        @param limit: 默认追加的安全截断行数（默认 100）
        @param dialect: 数据库方言标识（可选）
        @return: 经 AST 重写且注入 LIMIT 的安全 SQL 语句
        @throws SecurityViolationError: 包含写入操作、多语句拼接或语法错误时抛出
        """
        expr = cls._parse_and_validate_ast(sql, dialect=dialect)

        if expr.args.get("limit") is None:
            expr = expr.limit(limit)

        norm_dialect = cls._normalize_dialect(dialect)
        return expr.sql(dialect=norm_dialect)

    @classmethod
    def validate_dml_statements(
        cls,
        statements: str | list[str],
        dialect: str | None = None,
    ) -> list[str]:
        """校验单条或批量 DML 语句，并强制拦截缺少 WHERE 条件的 UPDATE/DELETE.

        @param statements: 单条 SQL 或 SQL 语句列表
        @param dialect: 数据库方言标识（可选）
        @return: 经校验合规的 SQL 语句列表
        @throws SecurityViolationError: 语句缺少 WHERE 条件、非 DML 操作或语法错误时抛出
        """
        # 1. 规格化输入为语句列表
        raw_list = [statements] if isinstance(statements, str) else statements
        if not raw_list:
            raise SecurityViolationError("DML 语句列表不能为空。")

        norm_dialect = cls._normalize_dialect(dialect)
        parsed_exprs: list[exp.Expression] = []

        # 2. 逐条解析语法树（强制每条仅限单语句，严禁分号注入多语句）
        for item in raw_list:
            stripped = item.strip().rstrip(";")
            if not stripped:
                continue
            try:
                exprs = sqlglot.parse(item, read=norm_dialect)
            except ParseError as exc:
                raise SecurityViolationError(f"DML 语法树解析失败: {exc}") from exc

            valid = [e for e in exprs if e is not None]
            if not valid:
                continue
            if len(valid) > 1:
                raise SecurityViolationError(
                    "为防止多语句注入，单条 SQL 字符串仅允许包含单条独立语句，批量执行请使用语句列表。"
                )
            parsed_exprs.extend(valid)

        if not parsed_exprs:
            raise SecurityViolationError("未能解析出任何有效的 DML 语句。")

        # 3. 校验每一条 DML 语句及其子节点
        for expr in parsed_exprs:
            # 校验顶层是否为合规的 DML 操作
            if not isinstance(expr, cls._ALLOWED_DML_ROOTS):
                raise SecurityViolationError(
                    f"sql_dml 仅允许执行数据增删改操作 (INSERT/UPDATE/DELETE)，"
                    f"检测到非法语句类型: {type(expr).__name__}。"
                )

            # 遍历子节点，杜绝任何嵌套 DDL 结构定义
            for node in expr.walk():
                if isinstance(node, cls._FORBIDDEN_DML_NODES):
                    raise SecurityViolationError(
                        f"DML 操作中禁止包含结构定义或破坏性 DDL 语句（检测到非法节点: {type(node).__name__}）。"
                    )

                # 核心防误删护栏：强制拦截缺少 WHERE 条件的 UPDATE 与 DELETE
                if isinstance(node, (exp.Update, exp.Delete)) and node.args.get("where") is None:
                    op = "UPDATE" if isinstance(node, exp.Update) else "DELETE"
                    raise SecurityViolationError(
                        f"为防止灾难性全表误改或误删，{op} 语句必须显式指定 WHERE 条件！"
                    )

        return [e.sql(dialect=norm_dialect) for e in parsed_exprs]

    @classmethod
    def validate_ddl_statement(
        cls,
        sql: str,
        dialect: str | None = None,
    ) -> str:
        """校验单条 DDL 结构定义语句的安全性与合法性.

        @param sql: 待校验的 DDL 语句
        @param dialect: 数据库方言标识（可选）
        @return: 经校验安全的 DDL SQL 语句
        @throws SecurityViolationError: 语句非 DDL、拼接多语句或语法错误时抛出
        """
        stripped = sql.strip().rstrip(";")
        if not stripped:
            raise SecurityViolationError("DDL 语句不能为空。")

        norm_dialect = cls._normalize_dialect(dialect)
        try:
            expressions = sqlglot.parse(sql, read=norm_dialect)
        except ParseError as exc:
            raise SecurityViolationError(f"DDL 语法树解析失败: {exc}") from exc

        valid_expressions = [e for e in expressions if e is not None]
        if not valid_expressions:
            raise SecurityViolationError("未能解析出任何有效的 DDL 语句。")

        if len(valid_expressions) > 1:
            raise SecurityViolationError("为防止多语句注入，严禁拼接执行多条 DDL 语句。")

        expr = valid_expressions[0]
        if not isinstance(expr, cls._ALLOWED_DDL_ROOTS):
            raise SecurityViolationError(
                f"sql_ddl 仅允许执行结构定义变更 (CREATE/ALTER/DROP/TRUNCATE)，"
                f"检测到非法语句类型: {type(expr).__name__}。"
            )

        return expr.sql(dialect=norm_dialect)
