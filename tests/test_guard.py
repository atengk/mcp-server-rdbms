"""
mcp-server-rdbms: AST 安全守卫与 LIMIT 注入测试.

@author Ateng
@since 2026-10-04
"""

import pytest

from atengk_mcp_server_rdbms.core.exceptions import SecurityViolationError
from atengk_mcp_server_rdbms.core.guard import ASTGuard


def test_simple_select_injects_limit():
    sql = "SELECT id, name FROM users"
    safe_sql = ASTGuard.validate_and_rewrite_query(sql, limit=100)
    assert "LIMIT 100" in safe_sql
    assert "SELECT id, name FROM users" in safe_sql


def test_select_preserves_existing_limit():
    sql = "SELECT id, name FROM users LIMIT 20"
    safe_sql = ASTGuard.validate_and_rewrite_query(sql, limit=100)
    assert "LIMIT 20" in safe_sql
    assert "LIMIT 100" not in safe_sql


def test_complex_cte_with_select_allowed():
    sql = """
    WITH user_orders AS (
        SELECT user_id, COUNT(*) as cnt
        FROM orders
        GROUP BY user_id
    )
    SELECT u.name, uo.cnt
    FROM users u
    JOIN user_orders uo ON u.id = uo.user_id
    """
    safe_sql = ASTGuard.validate_and_rewrite_query(sql, limit=50)
    assert "LIMIT 50" in safe_sql
    assert "WITH user_orders AS" in safe_sql


def test_multi_statement_blocked():
    sql = "SELECT * FROM users; DROP TABLE users;"
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_and_rewrite_query(sql)
    assert "多条" in str(exc_info.value) or "多语句" in str(exc_info.value)


@pytest.mark.parametrize(
    "forbidden_sql",
    [
        "INSERT INTO users (name) VALUES ('hacker')",
        "UPDATE users SET name = 'admin' WHERE id = 1",
        "DELETE FROM users WHERE id = 1",
        "DROP TABLE users",
        "CREATE TABLE test (id INT)",
        "ALTER TABLE users ADD COLUMN phone TEXT",
        "TRUNCATE TABLE users",
        "SELECT * INTO new_table FROM users",
    ],
)
def test_dml_and_ddl_blocked_for_query(forbidden_sql):
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_and_rewrite_query(forbidden_sql)
    assert "只读" in str(exc_info.value) or "禁止" in str(exc_info.value)


def test_cte_with_nested_delete_blocked():
    sql = "WITH d AS (DELETE FROM users WHERE id = 1 RETURNING *) SELECT * FROM d"
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_and_rewrite_query(sql)
    assert "只读" in str(exc_info.value) or "禁止" in str(exc_info.value)


def test_empty_sql_blocked():
    with pytest.raises(SecurityViolationError):
        ASTGuard.validate_and_rewrite_query("")

    with pytest.raises(SecurityViolationError):
        ASTGuard.validate_and_rewrite_query("   ;   ")


def test_validate_read_only_does_not_inject_limit():
    sql = "SELECT id, name FROM users"
    safe_sql = ASTGuard.validate_read_only(sql)
    assert "LIMIT" not in safe_sql
    assert "SELECT id, name FROM users" in safe_sql


def test_dml_valid_statements():
    stmts = [
        "INSERT INTO users (id, name) VALUES (1, 'alice')",
        "UPDATE users SET name = 'bob' WHERE id = 1",
        "DELETE FROM users WHERE id = 2",
    ]
    safe_stmts = ASTGuard.validate_dml_statements(stmts)
    assert len(safe_stmts) == 3


def test_dml_update_without_where_blocked():
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements("UPDATE users SET name = 'hacked'")
    assert "WHERE" in str(exc_info.value)


def test_dml_delete_without_where_blocked():
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements("DELETE FROM users")
    assert "WHERE" in str(exc_info.value)


def test_dml_ddl_blocked():
    with pytest.raises(SecurityViolationError):
        ASTGuard.validate_dml_statements("DROP TABLE users")

    with pytest.raises(SecurityViolationError):
        ASTGuard.validate_dml_statements("CREATE TABLE foo (id INT)")


def test_dml_multi_statement_in_single_str_blocked():
    """验证单条 SQL 字符串中分号拼接多语句注入被严格拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements(
            "UPDATE users SET name = 'a' WHERE id = 1; DELETE FROM users WHERE id = 2"
        )
    assert "多语句注入" in str(exc_info.value)


def test_dml_dialect_normalization_postgresql():
    """验证 SQLAlchemy 的 postgresql 方言自动归一化映射至 sqlglot 的 postgres."""
    stmts = ASTGuard.validate_dml_statements(
        "UPDATE users SET name = 'alice' WHERE id = 1",
        dialect="postgresql",
    )
    assert len(stmts) == 1
    assert "WHERE" in stmts[0]


def test_dml_merge_without_on_blocked():
    """验证 MERGE 语句缺少 ON 关联条件被拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements(
            "MERGE INTO target USING source WHEN MATCHED THEN DELETE"
        )
    assert "ON" in str(exc_info.value)



@pytest.mark.parametrize(
    "valid_ddl",
    [
        "CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(50))",
        "ALTER TABLE test ADD COLUMN age INT",
        "DROP TABLE test",
        "TRUNCATE TABLE test",
    ],
)
def test_ddl_valid_statements_allowed(valid_ddl: str):
    """验证合法的建表、改表、删表及截断 DDL 语句放行."""
    safe_sql = ASTGuard.validate_ddl_statement(valid_ddl)
    assert safe_sql.strip() != ""


@pytest.mark.parametrize(
    "invalid_ddl",
    [
        "SELECT * FROM test",
        "INSERT INTO test (id) VALUES (1)",
        "UPDATE test SET id = 2 WHERE id = 1",
        "DELETE FROM test WHERE id = 1",
    ],
)
def test_ddl_non_ddl_statements_blocked(invalid_ddl: str):
    """验证非 DDL 语句（查询、增删改）被拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_ddl_statement(invalid_ddl)
    assert "仅允许执行结构定义变更" in str(exc_info.value)


def test_ddl_multi_statement_blocked():
    """验证 DDL 中禁止拼接多条语句."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_ddl_statement("CREATE TABLE t1 (id INT); DROP TABLE t2")
    assert "严禁拼接执行多条" in str(exc_info.value)


def test_validate_explain_query_success():
    """验证合法的 SELECT 与带 EXPLAIN 前缀的语句正确放行并剥离修饰."""
    # 纯查询放行
    sql1 = ASTGuard.validate_explain_query("SELECT id, name FROM users WHERE id = 1")
    assert "SELECT id, name FROM users WHERE id = 1" in sql1

    # 带 EXPLAIN 前缀安全剥离并放行
    sql2 = ASTGuard.validate_explain_query("EXPLAIN SELECT id, name FROM users")
    assert "SELECT id, name FROM users" in sql2


def test_validate_explain_query_blocks_analyze_and_mutation():
    """验证 EXPLAIN 语句中带有 ANALYZE 修饰或包含写操作时强制拦截."""
    # 拦截 ANALYZE 修饰（防范真实执行写操作）
    with pytest.raises(SecurityViolationError) as exc1:
        ASTGuard.validate_explain_query("EXPLAIN ANALYZE SELECT * FROM users")
    assert "严禁包含 ANALYZE" in str(exc1.value)

    # 拦截 EXPLAIN INSERT
    with pytest.raises(SecurityViolationError) as exc2:
        ASTGuard.validate_explain_query("EXPLAIN INSERT INTO users (id) VALUES (1)")
    assert "只读查询中禁止包含修改" in str(exc2.value) or "不是支持的只读查询语句" in str(exc2.value)

    # 拦截纯写操作
    with pytest.raises(SecurityViolationError):
        ASTGuard.validate_explain_query("UPDATE users SET name = 'admin'")


def test_validate_explain_query_dialects_postgres_mysql_sqlite():
    """验证 SQLite、PostgreSQL 与 MySQL 多方言下的执行计划安全过滤与 LIMIT 禁注入."""
    # 1. PostgreSQL 方言：拦截 ANALYZE 与 EXECUTE
    with pytest.raises(SecurityViolationError) as exc_pg:
        ASTGuard.validate_explain_query(
            "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM users",
            dialect="postgres",
        )
    assert "ANALYZE" in str(exc_pg.value)

    # PostgreSQL 正常 EXPLAIN 放行且不追加 LIMIT
    pg_safe = ASTGuard.validate_explain_query(
        "EXPLAIN SELECT id, name FROM users",
        dialect="postgres",
    )
    assert "LIMIT" not in pg_safe.upper()
    assert "users" in pg_safe

    # 2. MySQL 方言：正常 EXPLAIN 放行且不追加 LIMIT，拦截写操作
    my_safe = ASTGuard.validate_explain_query(
        "EXPLAIN SELECT id, name FROM users",
        dialect="mysql",
    )
    assert "LIMIT" not in my_safe.upper()
    assert "users" in my_safe

    with pytest.raises(SecurityViolationError):
        ASTGuard.validate_explain_query(
            "EXPLAIN DELETE FROM users WHERE id = 1",
            dialect="mysql",
        )

    # 3. SQLite 方言：正常 EXPLAIN QUERY PLAN 放行且不追加 LIMIT
    sqlite_safe = ASTGuard.validate_explain_query(
        "EXPLAIN QUERY PLAN SELECT id FROM users",
        dialect="sqlite",
    )
    assert "LIMIT" not in sqlite_safe.upper()
    assert "users" in sqlite_safe



@pytest.mark.parametrize(
    "trivial_sql",
    [
        "UPDATE users SET name = 'x' WHERE 1 = 1",
        "UPDATE users SET name = 'x' WHERE true",
        "UPDATE users SET name = 'x' WHERE TRUE",
        "UPDATE users SET name = 'x' WHERE 1 = 1 OR 2 = 2",
        "UPDATE users SET name = 'x' WHERE 'a' = 'a'",
        "DELETE FROM users WHERE 1 = 1",
        "DELETE FROM users WHERE (1 = 1)",
        "DELETE FROM users WHERE 1 = 1 OR status = 'active'",
    ],
)
def test_dml_trivial_where_blocked(trivial_sql: str):
    """验证 UPDATE 和 DELETE 中完全退化为恒真的伪 WHERE 条件被严密拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements(trivial_sql)
    assert "恒真" in str(exc_info.value) or "WHERE" in str(exc_info.value)


@pytest.mark.parametrize(
    "valid_compound_sql",
    [
        "UPDATE users SET name = 'x' WHERE 1 = 1 AND id = 5",
        "UPDATE users SET name = 'x' WHERE id = 5 AND 1 = 1",
        "DELETE FROM users WHERE 1 = 1 AND status = 'inactive'",
        "DELETE FROM users WHERE status = 'inactive' AND (1 = 1 AND id > 10)",
    ],
)
def test_dml_compound_valid_where_allowed(valid_compound_sql: str):
    """验证带有动态脚手架但包含真实列过滤的合法复合条件放行."""
    safe_stmts = ASTGuard.validate_dml_statements(valid_compound_sql)
    assert len(safe_stmts) == 1
    assert "WHERE" in safe_stmts[0]


@pytest.mark.parametrize(
    "locking_sql",
    [
        "SELECT * FROM users FOR UPDATE",
        "SELECT id, name FROM users WHERE id = 1 FOR UPDATE",
        "SELECT * FROM users FOR SHARE",
        "SELECT * FROM users FOR UPDATE NOWAIT",
    ],
)
def test_query_locking_reads_blocked(locking_sql: str):
    """验证只读查询中包含 FOR UPDATE / FOR SHARE 等锁读修饰符被拒绝."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_and_rewrite_query(locking_sql)
    assert "锁读" in str(exc_info.value) or "UPDATE" in str(exc_info.value) or "乐观" in str(exc_info.value)


@pytest.mark.parametrize(
    "dangerous_func_sql",
    [
        "SELECT pg_sleep(5)",
        "SELECT sleep(5)",
        "SELECT nextval('user_id_seq')",
        "SELECT setval('user_id_seq', 100)",
        "SELECT lastval()",
        "SELECT pg_terminate_backend(12345)",
        "SELECT pg_cancel_backend(12345)",
        "SELECT pg_reload_conf()",
        "SELECT waitfor('00:00:05')",
    ],
)
def test_query_dangerous_functions_blocked(dangerous_func_sql: str):
    """验证只读查询中包含延时、序列变更及运维进程中断等高危内置函数被拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_and_rewrite_query(dangerous_func_sql)
    assert "高危" in str(exc_info.value) or "副作用" in str(exc_info.value)


def test_dml_merge_allowed_with_valid_on():
    """验证具备有效非恒真 ON 关联条件的 MERGE 语句正常放行."""
    merge_sql = (
        "MERGE INTO target USING source ON target.id = source.id "
        "WHEN MATCHED THEN UPDATE SET val = source.val"
    )
    safe_stmts = ASTGuard.validate_dml_statements(merge_sql)
    assert len(safe_stmts) == 1
    assert "MERGE" in safe_stmts[0].upper()


@pytest.mark.parametrize(
    "invalid_merge_sql",
    [
        "MERGE INTO target USING source ON 1 = 1 WHEN MATCHED THEN UPDATE SET val = source.val",
        "MERGE INTO target USING source ON true WHEN MATCHED THEN UPDATE SET val = source.val",
    ],
)
def test_dml_merge_trivial_on_blocked(invalid_merge_sql: str):
    """验证 MERGE 语句中包含恒真 ON 关联条件被强制拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements(invalid_merge_sql)
    assert "ON" in str(exc_info.value) and "恒真" in str(exc_info.value)


def test_dml_merge_trivial_when_condition_blocked():
    """验证 MERGE 语句中 WHEN 匹配分支包含恒真过滤条件被拦截."""
    sql = (
        "MERGE INTO target USING source ON target.id = source.id "
        "WHEN MATCHED AND 1 = 1 THEN DELETE"
    )
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements(sql)
    assert "恒真" in str(exc_info.value)


def test_ddl_locking_read_blocked():
    """验证 DDL 语句中嵌入的锁读修饰符被拒绝."""
    sql = "CREATE TABLE t AS SELECT * FROM users FOR UPDATE"
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_ddl_statement(sql)
    assert "锁读" in str(exc_info.value) or "UPDATE" in str(exc_info.value)




