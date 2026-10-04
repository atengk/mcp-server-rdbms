"""
mcp-server-rdbms: AST 安全守卫与 LIMIT 注入测试.

@author Ateng
@since 2026-10-04
"""

import pytest

from mcp_server_rdbms.core.exceptions import SecurityViolationError
from mcp_server_rdbms.core.guard import ASTGuard


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


def test_dml_merge_statement_blocked():
    """验证非基础增删改语句（如 MERGE）被拦截."""
    with pytest.raises(SecurityViolationError) as exc_info:
        ASTGuard.validate_dml_statements(
            "MERGE INTO target USING source ON target.id = source.id WHEN MATCHED THEN DELETE"
        )
    assert "仅允许执行数据增删改操作" in str(exc_info.value)


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


