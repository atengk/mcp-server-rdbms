"""
mcp-server-rdbms: 基于 sqlglot 的 AST 语法树安全分析与 LIMIT 注入守卫.

@author Ateng
@since 2026-10-04
"""

import re
from typing import ClassVar

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from atengk_mcp_server_rdbms.core.exceptions import SecurityViolationError


class ASTGuard:
    """AST 语法树安全守卫：只读性验证、防多语句拼接、自动 LIMIT 注入与 DML 条件防护.

    @author Ateng
    @since 2026-10-04
    """

    _EXPLAIN_PREFIX_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^\s*explain\s+", re.IGNORECASE)
    _DANGEROUS_EXPLAIN_MODIFIERS: ClassVar[re.Pattern[str]] = re.compile(
        r"\b(analyze|execute)\b", re.IGNORECASE
    )

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

    # 全 MCP 工具禁止使用排他或共享锁读修饰符的统一错误说明
    _LOCK_DISALLOWED_MESSAGE: ClassVar[str] = (
        "全 MCP 工具禁止包含排他或共享锁读修饰符（如 FOR UPDATE / FOR SHARE）。"
        "MCP 工具为无状态调用，请使用基于版本号的乐观并发控制（Optimistic Locking）。"
    )

    # 严禁在只读查询中调用的高危系统函数与具有副作用函数
    _DANGEROUS_FUNCTIONS: ClassVar[frozenset[str]] = frozenset({
        # 延时与拒绝服务
        "pg_sleep",
        "sleep",
        "waitfor",
        # 序列与状态递增
        "nextval",
        "setval",
        "lastval",
        # 进程与连接中断运维
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
    })

    # 允许作为 DML 数据操作的顶层 AST 节点类型（包含增删改及复合写 MERGE）
    _ALLOWED_DML_ROOTS: ClassVar[tuple[type[exp.Expression], ...]] = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Merge,
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

    @staticmethod
    def _unwrap_paren(node: exp.Expression | None) -> exp.Expression | None:
        """剥离外层嵌套括号表达式."""
        while isinstance(node, exp.Paren):
            node = node.this
        return node

    @classmethod
    def _is_trivial_true(cls, node: exp.Expression | None) -> bool:
        """判断表达式树是否在逻辑上完全退化为恒真表达式 (如 1=1, true, 1=1 OR 2=2).

        @param node: 待检测的 AST 表达式节点
        @return: 若完全退化为恒真返回 True，若包含真实列过滤约束返回 False
        """
        node = cls._unwrap_paren(node)
        if node is None:
            return True

        if isinstance(node, exp.Boolean):
            return bool(node.this)

        if isinstance(node, exp.Literal):
            try:
                val = int(node.this)
                return val != 0
            except (ValueError, TypeError):
                return False

        if isinstance(node, exp.EQ):
            left = cls._unwrap_paren(node.left)
            right = cls._unwrap_paren(node.right)
            return bool(left is not None and right is not None and left.sql() == right.sql())

        if isinstance(node, exp.NEQ):
            left = cls._unwrap_paren(node.left)
            right = cls._unwrap_paren(node.right)
            return bool(
                isinstance(left, exp.Literal)
                and isinstance(right, exp.Literal)
                and left.this != right.this
            )

        if isinstance(node, exp.Or):
            # 析取关系中，只要任意一侧完全恒真，整体即退化为恒真 (True OR Anything == True)
            return cls._is_trivial_true(node.left) or cls._is_trivial_true(node.right)

        if isinstance(node, exp.And):
            # 合取关系中，仅当两侧均为恒真时，整体才恒真；若包含真实列条件 (如 1=1 AND id=5) 则不为恒真
            return cls._is_trivial_true(node.left) and cls._is_trivial_true(node.right)

        return False


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
            # 1. 深度检测锁读修饰符节点
            if isinstance(node, exp.Lock):
                raise SecurityViolationError(cls._LOCK_DISALLOWED_MESSAGE)

            # 2. 深度检测高危系统函数与副作用函数
            if (
                isinstance(node, (exp.Anonymous, exp.Func))
                and node.name.lower() in cls._DANGEROUS_FUNCTIONS
            ):
                raise SecurityViolationError(
                    f"只读查询中禁止调用具有副作用或高危系统函数（检测到高危函数: {node.name}）。"
                )

            # 3. 深度检测禁止的写入与 DDL 节点
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
    def validate_explain_query(
        cls,
        sql: str,
        dialect: str | None = None,
    ) -> str:
        """执行计划语句安全校验：剥离前置 EXPLAIN 修饰并强制内层只读性检验.

        防范大模型意图误用 EXPLAIN ANALYZE 造成伴随真实写操作的严重安全漏洞。

        @param sql: 待校验的原始 SQL 文本（允许带或不带 EXPLAIN 前缀）
        @param dialect: 数据库方言标识（可选）
        @return: 剥离修饰符后经 AST 只读校验的安全 SQL 文本
        @throws SecurityViolationError: 包含 ANALYZE 修饰或底层非只读操作时抛出
        """
        stripped = sql.strip().rstrip(";")
        if not stripped:
            raise SecurityViolationError("SQL 查询语句不能为空。")

        # 检查是否包含危险的 ANALYZE / EXECUTE 修饰符
        if cls._DANGEROUS_EXPLAIN_MODIFIERS.search(stripped):
            raise SecurityViolationError(
                "EXPLAIN 语句中严禁包含 ANALYZE 或 EXECUTE 等修饰符，防范意外触发真实写入变更。"
            )

        # 若包含前置 EXPLAIN 关键字，剥离后提取纯查询语句
        inner_sql = cls._EXPLAIN_PREFIX_PATTERN.sub("", stripped).strip()
        if not inner_sql:
            raise SecurityViolationError("EXPLAIN 语句缺少待分析的底层查询内容。")

        # 对内层真实查询执行严格 AST 只读性验证
        return cls.validate_read_only(inner_sql, dialect=dialect)

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
                    f"sql_dml 仅允许执行数据增删改操作 (INSERT/UPDATE/DELETE/MERGE)，"
                    f"检测到非法语句类型: {type(expr).__name__}。"
                )

            # MERGE 语句专用守卫：校验 ON 关联条件非空且非恒真
            if isinstance(expr, exp.Merge):
                on_cond = expr.args.get("on")
                if on_cond is None or not on_cond:
                    raise SecurityViolationError("MERGE 语句必须显式指定 ON 关联条件！")
                if cls._is_trivial_true(on_cond):
                    raise SecurityViolationError(
                        "为防止灾难性全表覆写或误改，MERGE 语句的 ON 关联条件禁止为恒真表达式（如 ON 1=1）！"
                    )
                # 递归校验 WHEN 分支中可能附加的过滤条件
                for when in expr.find_all(exp.When):
                    when_cond = when.args.get("condition")
                    if when_cond is not None and cls._is_trivial_true(when_cond):
                        raise SecurityViolationError(
                            "MERGE 匹配分支的附加过滤条件禁止为恒真表达式（如 WHEN MATCHED AND 1=1）！"
                        )

            # 遍历子节点，杜绝任何嵌套 DDL 结构定义
            for node in expr.walk():
                if isinstance(node, cls._FORBIDDEN_DML_NODES):
                    raise SecurityViolationError(
                        f"DML 操作中禁止包含结构定义或破坏性 DDL 语句（检测到非法节点: {type(node).__name__}）。"
                    )

                if isinstance(node, exp.Lock):
                    raise SecurityViolationError(cls._LOCK_DISALLOWED_MESSAGE)

                # 核心防误删护栏：强制拦截缺少 WHERE 条件或退化为恒真条件的独立 UPDATE 与 DELETE
                # (MERGE 语句内部匹配分支由其外层的 ON 关联条件与 WHEN 过滤条件实施安全约束)
                if isinstance(node, (exp.Update, exp.Delete)) and node.find_ancestor(exp.Merge) is None:
                    where_clause = node.args.get("where")
                    op = "UPDATE" if isinstance(node, exp.Update) else "DELETE"
                    if where_clause is None:
                        raise SecurityViolationError(
                            f"为防止灾难性全表误改或误删，{op} 语句必须显式指定 WHERE 条件！"
                        )
                    if cls._is_trivial_true(where_clause.this):
                        raise SecurityViolationError(
                            f"为防止灾难性全表误改或误删，{op} 语句的 WHERE 条件禁止为恒真表达式（如 1=1、true 等）！"
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

        for node in expr.walk():
            if isinstance(node, exp.Lock):
                raise SecurityViolationError(cls._LOCK_DISALLOWED_MESSAGE)

        return expr.sql(dialect=norm_dialect)

