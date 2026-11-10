"""
mcp-server-rdbms: 只读查询与执行计划核心工具测试.

@author Ateng
@since 2026-10-04
"""

import time
from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text

from atengk_mcp_server_rdbms.core.connection import ConnectionRegistry
from atengk_mcp_server_rdbms.server import create_server
from atengk_mcp_server_rdbms.tools.sql_query import register_query_tools


@pytest.fixture
def query_setup():
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    engine = registry.get_engine("default")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                score NUMERIC NOT NULL,
                avatar BLOB
            );
        """))
        # 插入包含大 BLOB (> 1KB) 与普通数据的记录
        large_blob = b"a" * 2048
        conn.execute(
            text("INSERT INTO users (id, username, score, avatar) VALUES (:id, :name, :score, :avatar)"),
            [
                {"id": 1, "name": "alice", "score": 95.5, "avatar": b"small_img"},
                {"id": 2, "name": "bob", "score": 80.0, "avatar": large_blob},
            ],
        )
        conn.execute(text("""
            CREATE TABLE sensitive_users (
                id INTEGER PRIMARY KEY,
                password TEXT NOT NULL,
                phone TEXT NOT NULL,
                token_count INTEGER NOT NULL
            );
        """))
        conn.execute(
            text("INSERT INTO sensitive_users (id, password, phone, token_count) VALUES (1, 'plain_pwd', '13812345678', 10)")
        )
        conn.commit()

    server = MCPServer(name="test-server")
    register_query_tools(server, registry)
    return server, registry


@pytest.mark.asyncio
async def test_sql_query_json_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {"sql": "SELECT id, username, score FROM users ORDER BY id"})
    data = result.structured_content

    assert data["format"] == "json"
    assert data["row_count"] == 2
    assert data["columns"] == ["id", "username", "score"]
    rows = data["data"]
    assert rows[0]["username"] == "alice"
    assert rows[0]["score"] == 95.5
    assert rows[1]["username"] == "bob"


@pytest.mark.asyncio
async def test_sql_query_markdown_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {
        "sql": "SELECT id, username FROM users ORDER BY id",
        "format": "markdown",
    })
    data = result.structured_content

    assert data["format"] == "markdown"
    assert "| id | username |" in data["data"]
    assert "| 1 | alice |" in data["data"]


@pytest.mark.asyncio
async def test_sql_query_csv_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {
        "sql": "SELECT id, username FROM users ORDER BY id",
        "format": "csv",
    })
    data = result.structured_content

    assert data["format"] == "csv"
    lines = data["data"].strip().splitlines()
    assert lines[0] == "id,username"
    assert lines[1] == "1,alice"
    assert lines[2] == "2,bob"


@pytest.mark.asyncio
async def test_sql_query_blob_truncation(query_setup):
    server, _ = query_setup
    result = await server.call_tool("sql_query", {"sql": "SELECT id, avatar FROM users WHERE id = 2"})
    data = result.structured_content

    rows = data["data"]
    assert "<BLOB 2048 bytes:" in rows[0]["avatar"]
    assert "[truncated]>" in rows[0]["avatar"]


@pytest.mark.asyncio
async def test_sql_query_security_violations(query_setup):
    server, _ = query_setup

    # 1. 尝试执行 DML
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "DELETE FROM users WHERE id = 1"})
    assert "只读" in str(exc_info.value)

    # 2. 尝试执行 DDL
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "DROP TABLE users"})
    assert "只读" in str(exc_info.value)

    # 3. 尝试多语句拼接注入
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "SELECT 1; SELECT 2;"})
    assert "多条" in str(exc_info.value) or "多语句" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_timeout_breaker(query_setup):
    server, _ = query_setup

    def slow_exec(*args, **kwargs):
        time.sleep(0.1)
        return [], []

    with patch("atengk_mcp_server_rdbms.tools.sql_query._execute_query_sync", side_effect=slow_exec):
        with pytest.raises(ToolError) as exc_info:
            await server.call_tool("sql_query", {"sql": "SELECT * FROM users", "timeout": 0.01})
        assert "超时" in str(exc_info.value)




@pytest.mark.asyncio
async def test_sql_query_locking_reads_blocked(query_setup):
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "SELECT * FROM users FOR UPDATE"})
    assert "锁读" in str(exc_info.value) or "UPDATE" in str(exc_info.value) or "乐观" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_dangerous_function_blocked(query_setup):
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("sql_query", {"sql": "SELECT sleep(1)"})
    assert "高危" in str(exc_info.value) or "副作用" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_explain_sqlite_success(query_setup):
    server, _ = query_setup
    result = await server.call_tool(
        "sql_query",
        {"sql": "SELECT id, username FROM users WHERE id = 1", "explain": True},
    )
    data = result.structured_content

    assert data["format"] == "json"
    assert data["row_count"] > 0
    assert len(data["columns"]) > 0
    assert isinstance(data["data"], list)
    # SQLite EXPLAIN QUERY PLAN 返回的行包含 detail 字段
    assert any("detail" in row for row in data["data"])


@pytest.mark.asyncio
async def test_sql_query_explain_no_limit_injected(query_setup):
    server, _ = query_setup
    with patch("atengk_mcp_server_rdbms.tools.sql_query._execute_explain_sync", wraps=__import__("atengk_mcp_server_rdbms.tools.sql_query", fromlist=["_execute_explain_sync"])._execute_explain_sync) as spy_explain:
        await server.call_tool(
            "sql_query",
            {"sql": "SELECT * FROM users", "explain": True},
        )
        assert spy_explain.called
        # 校验传入底层执行的 SQL 不含 LIMIT
        passed_sql = spy_explain.call_args[0][1]
        assert "LIMIT" not in passed_sql.upper()


@pytest.mark.asyncio
async def test_sql_query_explain_markdown_format(query_setup):
    server, _ = query_setup
    result = await server.call_tool(
        "sql_query",
        {"sql": "SELECT * FROM users", "explain": True, "format": "markdown"},
    )
    data = result.structured_content

    assert data["format"] == "markdown"
    assert isinstance(data["data"], str)
    assert "|" in data["data"]
    assert "detail" in data["data"].lower() or "---" in data["data"]


@pytest.mark.asyncio
async def test_sql_query_explain_blocks_analyze(query_setup):
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_query",
            {"sql": "EXPLAIN ANALYZE SELECT * FROM users", "explain": True},
        )
    assert "ANALYZE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_explain_blocks_execute(query_setup):
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_query",
            {"sql": "EXPLAIN EXECUTE SELECT * FROM users", "explain": True},
        )
    assert "ANALYZE" in str(exc_info.value) or "EXECUTE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_explain_blocks_mutation(query_setup):
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_query",
            {"sql": "DROP TABLE users", "explain": True},
        )
    assert "只读" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_dml_remediation_guidance(query_setup):
    """测试 sql_query 拦截 DML 语句时输出自愈型指引并推荐 sql_dml."""
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_query",
            {"sql": "UPDATE users SET username = 'hacked' WHERE id = 1"},
        )
    err_msg = str(exc_info.value)
    assert "自愈指引" in err_msg
    assert "sql_dml" in err_msg
    assert "--allow-dml" in err_msg


@pytest.mark.asyncio
async def test_sql_query_ddl_remediation_guidance(query_setup):
    """测试 sql_query 拦截 DDL 语句时输出自愈型指引并推荐 sql_ddl."""
    server, _ = query_setup
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(
            "sql_query",
            {"sql": "ALTER TABLE users ADD COLUMN phone VARCHAR(20)"},
        )
    err_msg = str(exc_info.value)
    assert "自愈指引" in err_msg
    assert "sql_ddl" in err_msg
    assert "--allow-ddl" in err_msg


@pytest.mark.asyncio
async def test_sql_query_truncated_flag(query_setup):
    """测试 sql_query 正确返回 truncated 状态标识."""
    server, _ = query_setup
    # users 表中有 2 条数据，若设置 limit=1 则触发截断
    res_truncated = await server.call_tool(
        "sql_query",
        {"sql": "SELECT * FROM users", "limit": 1},
    )
    data_t = res_truncated.structured_content
    assert data_t["row_count"] == 1
    assert data_t["truncated"] is True

    # 若设置 limit=10，全量返回未截断
    res_not_truncated = await server.call_tool(
        "sql_query",
        {"sql": "SELECT * FROM users", "limit": 10},
    )
    data_nt = res_not_truncated.structured_content
    assert data_nt["row_count"] == 2
    assert data_nt["truncated"] is False


@pytest.mark.asyncio
async def test_sql_query_metrics_and_db_echo(query_setup):
    """测试 sql_query 正确返回 duration_ms、db、data_bytes 与 warning 契约."""
    server, _ = query_setup
    result = await server.call_tool(
        "sql_query",
        {"sql": "SELECT id, username FROM users ORDER BY id"},
    )
    data = result.structured_content

    assert "duration_ms" in data
    assert isinstance(data["duration_ms"], float)
    assert data["duration_ms"] >= 0.0
    # 验证保留两位小数
    assert data["duration_ms"] == round(data["duration_ms"], 2)

    assert data["db"] == "default"
    assert "data_bytes" in data
    assert data["data_bytes"] > 0
    assert data["warning"] is None


@pytest.mark.asyncio
async def test_sql_query_slow_query_warning(query_setup):
    """测试当查询耗时超出慢查询阈值时自动注入自愈预警."""
    server, _ = query_setup
    with patch("atengk_mcp_server_rdbms.tools.sql_query.get_slow_query_threshold_ms", return_value=0.0):
        result = await server.call_tool(
            "sql_query",
            {"sql": "SELECT id FROM users"},
        )
    data = result.structured_content
    assert data["warning"] is not None
    assert "当前查询耗时较长" in data["warning"]
    assert "explain=True" in data["warning"]


@pytest.mark.asyncio
async def test_sql_query_dynamic_timeout_threshold_convergence(query_setup):
    """测试当指定较小 timeout 时慢查询阈值自适应收敛至 timeout * 50%."""
    server, _ = query_setup
    # 模拟基础阈值为 1000ms，但 timeout=0.002s (2ms)，动态收敛为 1ms
    # 此时微小执行耗时即会超过 1ms 触发慢查询自愈提示
    result = await server.call_tool(
        "sql_query",
        {"sql": "SELECT id, username FROM users", "timeout": 0.002},
    )
    data = result.structured_content
    # 若执行耗时超过 1ms，则动态收敛预警生效
    if data["duration_ms"] >= 1.0:
        assert data["warning"] is not None
        assert "当前查询耗时较长" in data["warning"]



@pytest.mark.asyncio
async def test_sql_query_payload_size_warning(query_setup):
    """测试返回载荷超过 64KB 警戒线时自动提示按需投影."""
    server, _ = query_setup
    # SQLite 构造超过 64KB 且单字段不超 2048 字符的查询结果
    sql = "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x < 80) SELECT x, hex(randomblob(500)) AS content FROM cnt"
    result = await server.call_tool(
        "sql_query",
        {"sql": sql, "limit": 100},
    )
    data = result.structured_content
    assert data["data_bytes"] >= 65536
    assert data["warning"] is not None
    assert "返回数据体积较大" in data["warning"]
    assert "SELECT *" in data["warning"]


@pytest.mark.asyncio
async def test_sql_query_explain_table_scan_warning(query_setup):
    """测试 explain=True 时启发式检测全表扫描并提示索引覆盖."""
    server, _ = query_setup
    result = await server.call_tool(
        "sql_query",
        {"sql": "SELECT * FROM users WHERE score > 50", "explain": True},
    )
    data = result.structured_content
    assert data["warning"] is not None
    assert "全表扫描" in data["warning"]
    assert "Full Table Scan" in data["warning"]


@pytest.mark.asyncio
async def test_sql_query_custom_db_routing_echo(query_setup):
    """测试指定 db 参数时正确回显目标连接别名."""
    server, registry = query_setup
    registry.register_url("sqlite:///:memory:", name="analytics")
    engine = registry.get_engine("analytics")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE test_analytics (x INT);"))
        conn.commit()

    result = await server.call_tool(
        "sql_query",
        {"sql": "SELECT * FROM test_analytics", "db": "analytics"},
    )
    data = result.structured_content
    assert data["db"] == "analytics"


@pytest.mark.asyncio
async def test_sql_query_blocks_side_effecting_functions_end_to_end(query_setup):
    """测试 sql_query 顶层工具接口成功拦截副作用函数并返回 ToolError."""
    server, _ = query_setup

    with pytest.raises(ToolError) as exc_pg:
        await server.call_tool(
            "sql_query",
            {"sql": "SELECT pg_read_file('/etc/passwd')"},
        )
    assert "高危函数" in str(exc_pg.value) or "副作用" in str(exc_pg.value)

    with pytest.raises(ToolError) as exc_lo:
        await server.call_tool(
            "sql_query",
            {"sql": "SELECT lo_import('/etc/hostname')"},
        )
    assert "高危函数" in str(exc_lo.value) or "副作用" in str(exc_lo.value)


@pytest.mark.asyncio
async def test_sql_query_strict_functions_end_to_end(query_setup):
    """测试 create_server(strict_functions=True) 下的严格白名单模式."""
    _, registry = query_setup
    strict_server = create_server(registry, strict_functions=True)

    # 白名单函数正常放行
    res = await strict_server.call_tool(
        "sql_query",
        {"sql": "SELECT abs(score), lower(username) FROM users"},
    )
    assert res.structured_content["row_count"] == 2

    # 未注册自定义函数拦截
    with pytest.raises(ToolError) as exc_info:
        await strict_server.call_tool(
            "sql_query",
            {"sql": "SELECT custom_eval(id) FROM users"},
        )
    assert "严格函数模式" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sql_query_dynamic_masking_json_and_echo(query_setup):
    """测试 sql_query 默认执行动态数据脱敏并返回 masked_columns 回显."""
    server, _ = query_setup
    res = await server.call_tool(
        "sql_query",
        {"sql": "SELECT id, password, phone, token_count FROM sensitive_users"},
    )
    data = res.structured_content

    assert "masked_columns" in data
    assert data["masked_columns"] == ["password", "phone"]
    rows = data["data"]
    assert rows[0]["password"] == "******"
    assert rows[0]["phone"] == "138****5678"
    assert rows[0]["token_count"] == 10


@pytest.mark.asyncio
async def test_sql_query_dynamic_masking_markdown_and_csv(query_setup):
    """测试 markdown 与 csv 格式下脱敏与 masked_columns 回显保持一致."""
    server, _ = query_setup

    res_md = await server.call_tool(
        "sql_query",
        {
            "sql": "SELECT id, password, phone FROM sensitive_users",
            "format": "markdown",
        },
    )
    data_md = res_md.structured_content
    assert data_md["masked_columns"] == ["password", "phone"]
    assert "******" in data_md["data"]
    assert "138****5678" in data_md["data"]

    res_csv = await server.call_tool(
        "sql_query",
        {
            "sql": "SELECT id, password, phone FROM sensitive_users",
            "format": "csv",
        },
    )
    data_csv = res_csv.structured_content
    assert data_csv["masked_columns"] == ["password", "phone"]
    assert "******" in data_csv["data"]
    assert "138****5678" in data_csv["data"]


@pytest.mark.asyncio
async def test_sql_query_dynamic_masking_alias_bypass(query_setup):
    """测试别名重命名 SELECT phone AS col1 依然触发脱敏并回显被脱敏列名."""
    server, _ = query_setup
    res = await server.call_tool(
        "sql_query",
        {"sql": "SELECT phone AS col1 FROM sensitive_users"},
    )
    data = res.structured_content
    assert data["masked_columns"] == ["col1"]
    assert data["data"][0]["col1"] == "138****5678"


@pytest.mark.asyncio
async def test_sql_query_dynamic_masking_explain_mode_skips_columns(query_setup):
    """测试 explain 模式跳过列名脱敏且无脱敏时 masked_columns 返回空列表 []."""
    server, _ = query_setup
    res = await server.call_tool(
        "sql_query",
        {"sql": "SELECT id, username FROM users", "explain": True},
    )
    data = res.structured_content
    assert "masked_columns" in data
    assert data["masked_columns"] == []


@pytest.mark.asyncio
async def test_sql_query_masking_disabled_via_profile(query_setup):
    """测试在多库连接 Profile 中显式设置 mask_enabled=False 时展示明文."""
    server, registry = query_setup
    # 注册一个关闭脱敏的连接
    profile = registry.register_url("sqlite:///:memory:", name="dev_unmasked")
    profile.mask_enabled = False
    dev_engine = registry.get_engine("dev_unmasked")
    with dev_engine.connect() as conn:
        conn.execute(text("CREATE TABLE dev_data (phone TEXT, password TEXT);"))
        conn.execute(text("INSERT INTO dev_data VALUES ('13812345678', 'secret123');"))
        conn.commit()

    res = await server.call_tool(
        "sql_query",
        {"sql": "SELECT phone, password FROM dev_data", "db": "dev_unmasked"},
    )
    data = res.structured_content
    assert data["masked_columns"] == []
    assert data["data"][0]["phone"] == "13812345678"
    assert data["data"][0]["password"] == "secret123"


@pytest.mark.asyncio
async def test_sql_query_max_text_length_config():
    """测试 sql_query 在装配时指定 max_text_length 时的长文本截断与关闭截断行为."""
    registry = ConnectionRegistry()
    registry.register_url("sqlite:///:memory:", name="default")
    engine = registry.get_engine("default")
    long_content = "Z" * 500

    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE text_demo (id INT, content TEXT);"))
        conn.execute(
            text("INSERT INTO text_demo VALUES (1, :content);"),
            {"content": long_content},
        )
        conn.commit()

    # 1. 服务指定 max_text_length=50 触发截断
    server_limited = MCPServer(name="test-limited")
    register_query_tools(server_limited, registry, max_text_length=50)

    res_lim = await server_limited.call_tool("sql_query", {"sql": "SELECT content FROM text_demo"})
    data_lim = res_lim.structured_content
    assert data_lim["data"][0]["content"].startswith("Z" * 50)
    assert data_lim["data"][0]["content"].endswith("... [已截断，总长度 500 字符]")

    # 2. 服务指定 max_text_length=0 关闭截断（全量输出）
    server_unlimited = MCPServer(name="test-unlimited")
    register_query_tools(server_unlimited, registry, max_text_length=0)

    res_unlim = await server_unlimited.call_tool("sql_query", {"sql": "SELECT content FROM text_demo"})
    data_unlim = res_unlim.structured_content
    assert data_unlim["data"][0]["content"] == long_content







