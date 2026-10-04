# 更新日志 (Changelog)

本项目所有显著变更均记录于此文件中。
版本格式严格遵循 [语义化版本 2.0.0 (SemVer)](https://semver.org/lang/zh-CN/) 规范。

## [1.1.0] - 2026-10-04

### 🌟 核心特性与体验飞跃 (Major Enhancements)

#### 1. 独立环境变量原子拼装与特殊字符免手动转义 (🔥 核心亮点)
- **告别手工 URL 编码**：对于密码包含 `@`、`#`、`:`、`/` 等特殊字符的情况，支持直接在环境变量 `MCP_RDBMS_PASSWORD` 中填写原始明文密码，服务内置 RFC 1738 自动转义与防二次编码机制，彻底解决用户排错痛点；
- **全套原子字段自动组合**：支持单独配置方言 (`MCP_RDBMS_DIALECT`)、主机 (`MCP_RDBMS_DB_HOST`)、端口 (`MCP_RDBMS_DB_PORT`)、用户 (`MCP_RDBMS_USER`)、密码 (`MCP_RDBMS_PASSWORD`) 与数据库名 (`MCP_RDBMS_DATABASE`)，自适应组合成合规连接串；
- **驱动智能映射推导**：当未指定方言或驱动时，根据典型端口与方言名称自适应映射为最佳驱动（如 MySQL -> `mysql+pymysql`，PostgreSQL -> `postgresql+psycopg`，MSSQL -> `mssql+pyodbc`）。

#### 2. 12-Factor App 传输层环境变量与 100% 容器无参启动
- **通信协议与监听端口配置**：支持环境变量 `MCP_RDBMS_TRANSPORT`（`stdio` / `sse` / `streamable-http`）、`MCP_RDBMS_SERVER_HOST` / `HOST` 与 `MCP_RDBMS_SERVER_PORT` / `PORT`；
- **宽容布尔转换器**：权限门禁变量对 `1`, `true`, `yes`, `on`, `t`（大小写及首尾空格不敏感）实现可靠的归一化解析；
- **零依赖本地 `.env` 自动探测**：内置自适应加载当前工作目录下的 `.env` 文件，遵循“系统环境优先、不覆盖已有变量”防御原则，大幅加速本地自举开发。

#### 3. 执行计划 (sql_explain) AST 深度只读守卫与 ANALYZE 拦截
- **杜绝误写生产数据**：静态检测并强制拦截包含 `ANALYZE` 或 `EXECUTE` 等伴随真实写操作修饰符的 `EXPLAIN` 语句；
- **Prompt 异构性容错**：自动识别并剥离前置 `EXPLAIN` 关键字，提取内层纯查询语句送入语法树深度检验，完美兼顾大语言模型输入习惯与数据库执行计划的安全性。

#### 4. 生产级容器化资产 (Container Ecosystem)
- 新增官方生产级极速 `Dockerfile` 与 `docker-compose.yaml` 部署模板，预置轻量 Python 3.12 与全量驱动支持，方便在内网 NAS、私有云或 Docker 环境中一键拉起常驻 SSE 协议服务。

---

## [1.0.0] - 2026-10-04

### 🎯 架构概览与定位
`atengk-mcp-server-rdbms` 1.0.0 是通用的关系型数据库模型上下文协议（Model Context Protocol, MCP）官方正式首发版本。基于 Python、SQLAlchemy 2.0 与 FastMCP 现代化架构底座构建，专为大语言模型（LLM）提供标准、安全、可控、高内聚的多数据库探查、查询、诊断与变更能力。

---

### 🌟 核心特性与能力矩阵

#### 1. 精炼 9 核心工具契约 (9 Core Tools Matrix)
严格遵循领域前缀命名空间设计，杜绝工具冗余与二义性：
- **`db_list_connections`**: 查看已配置的所有数据库连接别名、方言内核、默认库标志及只读状态，密码强制实施 `***` 安全脱敏掩码。
- **`db_get_info`**: 探查目标数据库内核方言、真实版本号、当前 Schema/Database 及活跃登录用户。
- **`schema_list_tables`**: 一站式获取业务表/视图清单、表注释并自动聚合跨表外键依赖拓扑，底层自动拦截数据库系统保留模式。
- **`schema_describe_table`**: 一站式全息探查数据表列明细（类型、可空性、默认值）、主键约束、外键关联与全部索引明细。
- **`sql_query`**: 安全只读查询与数据采样，支持复杂 CTE `WITH` 语法，支持输出 `json`、`markdown` 与 `csv` 三种格式，并对 Decimal、时间及超大 BLOB 进行安全序列化。
- **`sql_explain`**: 执行 `EXPLAIN` 语句获取底层执行计划，辅助分析长查询与索引命中瓶颈。
- **`sql_dml`**: 原子事务数据增删改，支持单条与批量 SQL。底层运行在单一原子事务中，单步失败全量自动回滚；AST 强制拦截缺少 `WHERE` 条件的 `UPDATE`/`DELETE` 误操作。
- **`sql_ddl`**: 结构定义变更（建表、删表、改表），受独立权限门禁与 `confirm=True` 二次确认保护。
- **`admin_list_running_queries`**: 观测数据库正在运行的长查询与活动会话（针对 SQLite 等轻量库自适应优雅降级）。

#### 2. AST 级深度安全守卫 (Guardrail System)
- **语法树零绕过拦截**: 基于 `sqlglot` 将查询解析为 AST 抽象语法树，物理阻断包含多语句拼接（SQL 注入防御）以及只读操作中夹带的任何写操作。
- **自适应 LIMIT 截断注入**: 对未显式指定 `LIMIT` 的只读查询，在 AST 层强制注入安全截断限制，杜绝全表拉取导致 OOM 或上下文爆炸。
- **灾难性误删阻断**: 静态 AST 分析强制拦截无 `WHERE` 条件的 `UPDATE` 与 `DELETE` 语句，直接驳回。
- **独立审计日志落盘**: 所有 DDL 与 DML 变更尝试均全量异步记录至本地 `rdbms_mcp_audit.log` 审计流水中。

#### 3. 异步防阻塞与连接池自愈 (Async Offloading & Pool Healing)
- FastMCP 异步事件循环与同步 SQLAlchemy 引擎解耦，全部数据库 I/O 统一通过 `anyio.to_thread.run_sync` 卸载至工作线程池执行。
- 连接池集成 `pool_pre_ping=True` 探针预检与周期回收机制，毫秒级自愈因外部超时或重启产生的断连/死连接。

#### 4. 多数据库与多方言开箱即用
- 默认内置集成 **SQLite**、**PostgreSQL** (`psycopg3`)、**MySQL** (`pymysql`) 驱动。
- 采用插件化驱动扩展架构，针对缺失驱动（如 Oracle、SQL Server、ClickHouse）提供友好的自适应引导与智能拦截。

---

### ⚡ 快速上手与客户端配置

#### 1. 使用 `uvx` 免安装直接启动（推荐）
```bash
# 单库直接运行
uvx atengk-mcp-server-rdbms --db-url "postgresql+psycopg://user:password@localhost:5432/mydb"

# 使用多库配置文件启动
uvx atengk-mcp-server-rdbms --config ./connections.yaml
```

#### 2. Claude Desktop 配置指南
在配置文件中添加：
```json
{
  "mcpServers": {
    "rdbms": {
      "command": "uvx",
      "args": [
        "atengk-mcp-server-rdbms",
        "--db-url",
        "mysql+pymysql://root:password@127.0.0.1:3306/mydb?charset=utf8mb4"
      ]
    }
  }
}
```

#### 3. 启用写入权限（安全写模式）
若需要允许大模型执行数据修改或结构变更，显式传入 `--allow-dml` 与 `--allow-ddl` 参数：
```json
{
  "mcpServers": {
    "rdbms-write": {
      "command": "uvx",
      "args": [
        "atengk-mcp-server-rdbms",
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

### 🧩 扩展方言驱动安装指南
- **Oracle**: `uv pip install "atengk-mcp-server-rdbms[oracle]"`
- **SQL Server**: `uv pip install "atengk-mcp-server-rdbms[mssql]"`
- **ClickHouse**: `uv pip install "atengk-mcp-server-rdbms[clickhouse]"`
- **全量驱动**: `uv pip install "atengk-mcp-server-rdbms[all]"`

---

### 🛡️ 质量保障
- 包含 120 个端到端单元测试与纯算法 AST 解析测试用例，全量通过（100% Pass）。
- 经受真实公网 MySQL 8.4 LTS 9 核心工具全生命周期严苛联调验证。
