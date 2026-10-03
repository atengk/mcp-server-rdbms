# mcp-server-rdbms

通用的关系型数据库模型上下文协议（Model Context Protocol, MCP）服务，基于 Python、SQLAlchemy 2.0 与 FastMCP 构建。专为大语言模型（LLM）提供安全、可控、高内聚的多数据库探查、查询、诊断与变更能力。

---

## 🌟 核心特性

- 🚀 **通用多数据库抽象**：基于 SQLAlchemy 2.0 底座，默认支持 **SQLite**、**PostgreSQL**、**MySQL**，并可通过驱动扩展无缝接入 **Oracle**、**SQL Server**、**ClickHouse** 及各类符合标准方言的国产数据库。
- 🛡️ **AST 级深度安全守卫**：
  - 基于 `sqlglot` 语法树静态分析，只读模式下物理拦截任何 DDL/DML/注入操作；
  - 自动为大模型查询注入 `LIMIT` 截断，彻底杜绝全表拉取导致 OOM；
  - DML 操作强制校验 `WHERE` 条件，杜绝无条件全表 `UPDATE` 或 `DELETE` 误操作。
- ⚡ **原子事务与安全变更**：
  - `sql_dml` 原生支持单条或多条 SQL 批处理，底层默认运行在独立事务中，出错全量自动回滚；
  - DML 与 DDL 细粒度权限隔离，默认强只读，写权限需通过启动参数显式授权。
- 🔍 **精炼 9 核心工具矩阵**：无二义性、零冗余设计，工具按领域命名空间规范组织，模型理解与调用准确率极高。
- 🌐 **多数据库配置中心**：支持单库环境变量（`DATABASE_URL`）直连，亦支持通过 YAML/JSON 配置文件多库路由与密码脱敏探查。

---

## 🛠️ 9 核心工具矩阵

| 领域前缀 | 工具名称 | 参数契约 | 功能描述 |
| :--- | :--- | :--- | :--- |
| **`db_`** | `db_list_connections` | `()` | 查看所有已配置的数据库连接别名、方言、只读状态与脱敏 URL |
| | `db_get_info` | `(db: str = None)` | 获取数据库方言、内核版本、当前 Schema/Database 及当前登录用户 |
| **`schema_`** | `schema_list_tables` | `(db=None, schema=None, include_views=True)` | 获取所有数据表与视图清单、注释及外键拓扑关系图谱 |
| | `schema_describe_table` | `(table_name: str, db=None, schema=None)` | 一站式查询指定表的列定义、数据类型、可空性、主外键约束与索引明细 |
| **`sql_`** | `sql_query` | `(sql: str, limit: int = 100, format="json", db=None)` | 安全只读查询，承担数据预览、样本采样与业务数据分析（支持 CTE `WITH` 语法） |
| | `sql_explain` | `(sql: str, db=None)` | 执行 `EXPLAIN` 获取查询执行计划，辅助诊断慢查询与索引命中情况 |
| | `sql_dml` | `(sql: str \| list[str], confirm: bool = False, db=None)` | 数据增删改。**默认原子事务**，支持单条或批量，出错全量回滚，禁止无 WHERE 变更 |
| | `sql_ddl` | `(sql: str, confirm: bool = False, db=None)` | 结构变更（建表、删表、改表）。受独立 `--allow-ddl` 权限管控 |
| **`admin_`** | `admin_list_running_queries` | `(db=None)` | 查看当前正在运行的长查询与阻塞会话（不支持的库自适应优雅降级） |

---

## 📦 安装与快速运行

### 方式 1：使用 `uvx` 免安装直接运行（推荐）

无需在本地克隆代码或手动创建虚拟环境，使用现代 Python 包管理器 `uv` 即可直接拉取并启动：

```bash
# 单库直接运行（指定数据库连接串）
uvx mcp-server-rdbms --db-url "postgresql+psycopg://user:password@localhost:5432/mydb"

# 使用多库配置文件启动
uvx mcp-server-rdbms --config ./connections.yaml
```

### 方式 2：本地源码克隆与运行

```bash
# 克隆仓库
git clone https://github.com/atengk/mcp-server-rdbms.git
cd mcp-server-rdbms

# 使用 uv 安装核心依赖
uv sync

# 启动服务
uv run mcp-server-rdbms --db-url "sqlite:///./demo.db"
```

---

## 🔌 MCP 客户端接入配置

### 1. Claude Desktop 配置

在 Claude Desktop 配置文件（Windows: `%APPDATA%\Claude\claude_desktop_config.json`，macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`）中添加：

```json
{
  "mcpServers": {
    "rdbms": {
      "command": "uvx",
      "args": [
        "mcp-server-rdbms",
        "--db-url",
        "postgresql+psycopg://user:password@localhost:5432/mydb"
      ]
    }
  }
}
```

### 2. 启用数据变更权限（写模式）

若需允许大模型执行 DML（数据增删改）或 DDL（建表/改表），请显式传入授权参数：

```json
{
  "mcpServers": {
    "rdbms-write": {
      "command": "uvx",
      "args": [
        "mcp-server-rdbms",
        "--config",
        "/path/to/connections.yaml",
        "--allow-dml",
        "--allow-ddl"
      ]
    }
  }
}
```

---

## 🧩 数据库驱动扩展

`mcp-server-rdbms` 默认内置了 SQLite、PostgreSQL、MySQL 驱动。若需连接其他数据库：

| 目标数据库 | 安装扩展命令 | 连接串 Scheme 示例 |
| :--- | :--- | :--- |
| **Oracle** | `uv pip install "mcp-server-rdbms[oracle]"` | `oracle+oracledb://user:pass@host:1521/?service_name=orcl` |
| **SQL Server** | `uv pip install "mcp-server-rdbms[mssql]"` | `mssql+pyodbc://user:pass@host:1433/db?driver=...` |
| **ClickHouse** | `uv pip install "mcp-server-rdbms[clickhouse]"` | `clickhouse+native://user:pass@host:9000/db` |
| **其他方言** | `uv pip install <sqlalchemy-dialect-package>` | 直接配置对应 SQLAlchemy URL 即可动态接入 |

---

## 📄 开源许可证

本项目采用 [MIT 许可证](LICENSE) 开源。
