# atengk-mcp-server-rdbms

<p align="center">
  <a href="https://pypi.org/project/atengk-mcp-server-rdbms/"><img src="https://img.shields.io/pypi/v/atengk-mcp-server-rdbms.svg?color=blue&label=PyPI" alt="PyPI version"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/releases"><img src="https://img.shields.io/github/v/release/atengk/mcp-server-rdbms?style=flat-square&color=blue&label=Release" alt="GitHub Release"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/atengk/mcp-server-rdbms/ci.yml?branch=main&label=CI&style=flat-square" alt="CI Status"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/actions"><img src="https://img.shields.io/badge/tests-217%20passed-brightgreen.svg?style=flat-square" alt="Tests"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-1.1.0-purple.svg?style=flat-square" alt="MCP Protocol"></a>
  <a href="./CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome"></a>
  <a href="./CODE_OF_CONDUCT.md"><img src="https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg?style=flat-square" alt="Contributor Covenant"></a>
  <a href="./SECURITY.md"><img src="https://img.shields.io/badge/Security-Responsible%20Disclosure-brightgreen.svg?style=flat-square" alt="Security Policy"></a>
</p>

通用的关系型数据库模型上下文协议（Model Context Protocol, MCP）官方服务，基于 **Python 3.12+**、**SQLAlchemy 2.0** 与 **FastMCP** 现代化架构构建。专为各类大语言模型（LLM）与智能体（Claude、Cursor、Windsurf、Dify 等）提供标准、安全、可控、高内聚的多数据库探查、查询采样、慢查询诊断与原子事务变更能力。

---

## 🌟 核心特性与架构底座

### 🏗️ 系统全景架构拓扑 (Architecture Topology)

```mermaid
flowchart TD
    subgraph ClientSide ["AI 客户端生态 (MCP Client)"]
        Client["Claude Desktop / Cursor / VS Code / Dify / Windsurf"]
    end

    subgraph ProtocolLayer ["通信传输、自解释元数据与环境层"]
        FastMCP["FastMCP 协议服务器 (stdio / sse / streamable-http)"]
        Meta["服务元数据自解释 (--server-name / --server-instructions)"]
        Doctor["健康体检探针与版本反射 (--doctor / --version)"]
        Env["分层环境解析器 (core/env.py)"]
        Dotenv[".env 自动探测与 RFC 1738 密码免转义拼装"]
    end

    subgraph GuardLayer ["AST 深度语法安全守卫 (core/guard.py)"]
        ASTParse["sqlglot AST 语法树解析与分析"]
        ReadOnly["只读语义校验 (Select / CTE With)"]
        LimitInject["自动注入安全 LIMIT 截断 (默认 100 行)"]
        WhereGuard["DML 强制阻断无 WHERE 条件与恒真伪条件"]
        ExplainGuard["sql_query explain 危险修饰符 (ANALYZE) 拦截与剥离"]
    end

    subgraph EngineLayer ["连接池、分级审计与多库路由中枢 (core/)"]
        Registry["ConnectionRegistry (多库配置中心)"]
        Pool["连接池健康预检与自愈 (pool_pre_ping)"]
        Audit["分级审计与防爆截断器 (mutation/all/off, 4096 字符截断)"]
        Resources["MCP 只读资源暴露器 (rdbms://connections, schema, audit)"]
    end

    subgraph DatabaseLayer ["多元关系型数据库集群 (SQLAlchemy 2.0)"]
        MySQL[("MySQL 8.x / 5.7 / MariaDB")]
        PostgreSQL[("PostgreSQL 12~17")]
        SQLite[("SQLite 内存库 / 本地文件库")]
        Oracle[("Oracle 19c / 21c")]
        MSSQL[("SQL Server / ClickHouse / 国产库")]
    end

    Client -->|"JSON-RPC / SSE"| FastMCP
    FastMCP --> Meta
    Doctor -.-> Registry
    Dotenv --> Env --> Registry
    FastMCP -->|"6 核心工具调用 (带多库路由引导)"| GuardLayer
    FastMCP -->|"3 大 MCP 只读资源"| Resources
    GuardLayer -->|"AST 验证通过"| Registry
    Registry --> Pool
    Pool -->|"工作线程池异步卸载 (anyio)"| DatabaseLayer
    Registry -.->|"审计流水异步落盘"| Audit
```

- 🚀 **通用多数据库抽象底座**：
  - 基于 SQLAlchemy 2.0 驱动引擎，默认内置 **SQLite**、**PostgreSQL** (`psycopg3`)、**MySQL** (`pymysql`)；
  - 插件化扩展无缝支持 **Oracle**、**SQL Server**、**ClickHouse** 及各类符合标准方言的国产数据库（达梦、人大金仓等）。
- 🩺 **开箱即用健康体检与自检探针 (`--doctor` / `--version`)**：
  - 集成全方位体检探针，秒级扫描 9 大驱动就绪矩阵、检测被废弃通用变量以防意外串库、并对数据库进行 Ping 握手探活；
  - 默认以 Rich 彩色终端卡片呈现，支持 `--format json` 便于自动化 CI/CD 巡检集成。
- 🛡️ **AST 语法树级深度安全守卫 (Guardrail)**：
  - 基于 `sqlglot` 语法树静态分析，只读模式下物理拦截任何多语句拼接（SQL 注入防御）以及非 SELECT/WITH 写入操作；
  - **自动 LIMIT 注入**：为未指定行数的大模型查询强制追加安全截断（默认 100 行），彻底杜绝全表拉取导致 OOM 或上下文爆炸；
  - **灾难性误改误删阻断**：静态分析强制拦截缺少 `WHERE` 条件或退化为恒真条件（如 `1=1`、`true`）的 `UPDATE` 与 `DELETE` 语句，直接驳回。
- ⚡ **原子事务与权限双重门禁**：
  - `sql_dml` 接受单条或批量 SQL，底层在**单一原子事务块**中执行，任何单步失败全量自动 `ROLLBACK`，绝不留脏数据；
  - 默认强只读保护，写权限必须通过 `--allow-dml` 与 `--allow-ddl` 显式授权，且 DDL 建表/删表要求 `confirm=True` 二次确认。
- 🌐 **多数据库双模解耦与路由引导**：
  - **单实例多库**：全部工具描述注入强引导提示词，大模型可结合 `rdbms://connections` 资源通过 `db` 参数精准调度；
  - **多实例挂载**：支持通过 `--server-name` 与 `--server-instructions` 注入业务元数据，彻底消灭大模型在多服务实例下的理解歧义。
- 📝 **分级审计流水与防爆截断保护**：
  - 支持 `mutation`（仅写操作）、`all`（全量含只读分析）与 `off`（关闭）三档分级模式；
  - 具备 4096 字符长语句折叠与批量 100 条智能截断，物理级防御大文本打爆磁盘；通过 `rdbms://audit/recent` 供模型自主追溯。

---

## 🛠️ 6 核心工具矩阵全景契约

服务严格恪守“精炼 6 核心工具契约”，杜绝工具蔓延。所有工具均在描述中内置多库路由引导，支持可选的 `db` 参数（不传自动路由到默认连接；传入时精准定位目标库）：

| 领域前缀 | 工具名称 | 参数契约 | 功能描述与安全约束 |
| :--- | :--- | :--- | :--- |
| **`db_`** | `db_info` | `(db: str = None)` | 一站式探查数据库内核版本、当前 Schema/用户、只读保护及全部已配置连接别名列表（密码强制 `***` 掩码脱敏）。多库环境下可供大模型快速发现可用数据库 |
| **`schema_`** | `schema_list_tables` | `(schema=None, pattern=None, include_views=False, include_foreign_keys=False, db=None)` | 获取业务数据表与视图清单、表注释并支持模式过滤与可选外键依赖拓扑分析。支持多数据库路由，自动过滤底层系统保留模式 |
| | `schema_describe_table` | `(table_name: str, schema=None, db=None)` | 一站式全息探查数据表列明细（类型、可空性、默认值）、主键约束、外键关联与全部索引明细。支持多数据库路由 |
| **`sql_`** | `sql_query` | `(sql: str, limit: int = 100, format="json", explain: bool = False, db=None)` | 安全只读数据采样与业务分析，支持复杂 CTE `WITH` 语法与多库路由。支持 `json` / `markdown` / `csv` 格式、长文本自动截断与自愈型重定向指引；`explain=True` 时内生获取执行计划 |
| | `sql_dml` | `(sql: str \| list[str], db=None)` | 原子事务数据增删改（支持单条、批量与 MERGE，支持多库路由）。**单步失败全量自动回滚**，受 `--allow-dml` 门禁管控，**强制拦截无 WHERE 条件与恒真操作** |
| | `sql_ddl` | `(sql: str, confirm: bool = False, db=None)` | 结构定义变更（建表、删表、改表，支持多库路由）。受 `--allow-ddl` 权限管控并要求 `confirm=True` 二次确认 |

---

## 📚 MCP 只读资源 (Resources) 契约

服务全面接入标准 MCP Resources 协议，为支持资源挂载的 AI 客户端（如 Claude Desktop、Cursor 等）提供零 Tool Call 秒级注入数据库上下文与自省能力：

| 资源 URI / 模板 | 类型 | 传输格式 | 功能说明与容灾表现 |
| :--- | :--- | :--- | :--- |
| `rdbms://connections` | 静态资源 | `application/json` | 输出当前所有已配置数据库连接别名、方言内核、默认库标记与只读状态（密码强制 `***` 掩码脱敏），供大模型预装载全局连接认知 |
| `rdbms://{db}/schema` | 动态模板 | `application/json` | 按需获取指定连接的数据库模式名、业务表与视图清单概要及注释。当目标连接不可达时优雅降级返回 `status: "error"` 与错误原因，不导致协议崩溃 |
| `rdbms://audit/recent` | 静态资源 | `application/json` | 查看服务近期执行的 SQL 操作与审计流水（默认返回最近 50 条），支持防爆截断与优雅容灾降级返回空数组 |

---

## 📦 快速安装与运行

推荐使用现代化 Python 工具 [`uv`](https://docs.astral.sh/uv/) / `uvx`，无需在本地手动克隆代码或配置 Python 虚拟环境，一行命令即可秒级启动：

```bash
# 1. 单数据库直连启动 (只读安全模式)
uvx atengk-mcp-server-rdbms --db-url "postgresql+psycopg://user:password@localhost:5432/mydb"

# 2. 多数据库配置文件启动
uvx atengk-mcp-server-rdbms --config ./connections.yaml

# 3. 开启写入权限 (允许 DML 与 DDL)
uvx atengk-mcp-server-rdbms --db-url "sqlite:///./demo.db" --allow-dml --allow-ddl
```

若需从本地源码运行：
```bash
git clone https://github.com/atengk/mcp-server-rdbms.git
cd mcp-server-rdbms
uv sync
uv run atengk-mcp-server-rdbms --db-url "sqlite:///./demo.db"
```

---

## 🩺 命令行自检与运维诊断 (--doctor / --version)

服务内置全方位健康体检探针，帮助开发者在接入 Claude Desktop、Cursor 或云端容器前秒级排查驱动缺失、环境变量语法错误与网络连通性阻断：

```bash
# 1. 执行全方位自检探针 (诊断本地驱动就绪矩阵、命名空间合规性与连通性)
uvx atengk-mcp-server-rdbms --doctor

# 2. 携带目标数据库连接执行真实握手探活 (测试网络通畅度与账号权限)
uvx atengk-mcp-server-rdbms --db-url "postgresql+psycopg://user:password@localhost:5432/mydb" --doctor

# 3. 机器可读模式 (输出 JSON，便于 CI/CD 自动化流水线集成)
uvx atengk-mcp-server-rdbms --doctor --format json

# 4. 显示服务版本、Python 运行时、SQLAlchemy 版本与操作系统基线
uvx atengk-mcp-server-rdbms --version
```

### 终端高保真体检输出预览 (Terminal Card Preview)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ MCP Server RDBMS 运行环境与健康体检探针 (Doctor Diagnostics)                │
│ 服务版本: 1.2.2 | Python: 3.12.14 (CPython) | SQLAlchemy: 2.1.3 | SQLGlot:  │
│ 30.21.0                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                          1. 关系型数据库驱动就绪矩阵                          
┌─────────────────────┬────────────────────┬────────────┬─────────────────────┐
│ 目标方言            │ 对应驱动包         │  就绪状态  │ 驱动版本 / 安装指引 │
├─────────────────────┼────────────────────┼────────────┼─────────────────────┤
│ sqlite              │ sqlite3            │  [✓] 就绪  │ 3.12.14             │
│ mysql / mariadb     │ pymysql            │  [✓] 就绪  │ 1.2.3               │
│ postgresql          │ psycopg            │  [✓] 就绪  │ 3.3.6               │
│ oracle              │ oracledb           │ [!] 未安装 │ 可选驱动未安装。如… │
│ mssql (SQL Server)  │ pyodbc             │ [!] 未安装 │ 可选驱动未安装。如… │
│ clickhouse          │ clickhouse-connect │ [!] 未安装 │ 可选驱动未安装。如… │
│ dm (达梦)           │ dmPython           │ [!] 未安装 │ 可选驱动未安装。如… │
│ kingbase (人大金仓) │ ksycopg2           │ [!] 未安装 │ 可选驱动未安装。如… │
└─────────────────────┴────────────────────┴────────────┴─────────────────────┘

                       2. 环境变量命名空间与配置合规审计                       
┌──────────────────────────┬──────────┬───────────────────┬───────────────────┐
│ 审计检测项               │   状态   │ 取值 / 命中       │ 合规诊断明细与建议│
├──────────────────────────┼──────────┼───────────────────┼───────────────────┤
│ 通用无前缀环境变量扫描   │ [✓] 合规 │ 合规              │ 未发现导致意外串库│
│ MCP_RDBMS_* 专属变量纳管 │ [✓] 合规 │ 2 项生效          │ 当前环境生效 2 项 │
│ 单库连接串语法合法性     │ [✓] 合规 │ postgresql+psy... │ URL 语法校验通过  │
└──────────────────────────┴──────────┴───────────────────┴───────────────────┘

                          3. 数据库连接握手与探活探针                          
┌──────────┬────────────┬───────────────────────┬──────────┬──────────────────┐
│ 连接别名 │ 方言       │ 连接串 (脱敏)         │  连通性  │ 延迟 / 错误原因  │
├──────────┼────────────┼───────────────────────┼──────────┼──────────────────┤
│ default  │ postgresql │ postgresql+psycopg... │ [✓] 通畅 │ 14.25 ms (Ping)  │
└──────────┴────────────┴───────────────────────┴──────────┴──────────────────┘

┌────────────────────── ✓ 诊断通过：环境与服务状态健康 ───────────────────────┐
│ 全部核心诊断项通过，运行环境与数据库连接通畅。                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 探针覆盖的三大核心维度：
1. **驱动支持矩阵 (Driver Matrix)**：静态安全嗅探 9 大关系型数据库方言驱动支持度，精准输出一键安装命令；
2. **专属命名空间审计 (Namespace Hygiene)**：排查宿主环境是否存在被废弃或易混淆的通用无前缀变量（如 `DATABASE_URL`），主动告警其已被安全忽略，物理防御跨进程串库；
3. **连接握手探活探针 (Connection Probe)**：对配置的连接建立真实短连接并执行 `SELECT 1`，输出毫秒级响应延迟与错误根因（凭据密码自动 `***` 脱敏）。

---

## 🔌 MCP 客户端通用标准配置

> 💡 **提示**：以下配置完全遵循 Model Context Protocol (MCP) 官方开放规范，适用于 **Claude Desktop**、**Cursor**、**Windsurf**、**VS Code** 以及任何兼容 MCP 协议的 AI 客户端。

### 场景 1：单数据库标准本地调用 (stdio 协议，推荐)

在客户端 MCP 配置文件（如 `mcp.json` 或 `claude_desktop_config.json`）的 `"mcpServers"` 块中添加：

#### 模式 A-1：原子字段模式（🔥 强烈推荐 ⭐⭐⭐⭐⭐，密码特殊字符免手动转义！）
> 针对密码包含 `@`、`#`、`:` 等特殊字符的情况，**直接填写明文密码即可**！服务内置环境自动拼装器会自动进行 RFC 1738 安全转义，再也无需手工查表编码！

```json
{
  "mcpServers": {
    "rdbms": {
      "command": "uvx",
      "args": ["atengk-mcp-server-rdbms"],
      "env": {
        "MCP_RDBMS_DIALECT": "mysql",
        "MCP_RDBMS_DB_HOST": "127.0.0.1",
        "MCP_RDBMS_DB_PORT": "3306",
        "MCP_RDBMS_USER": "root",
        "MCP_RDBMS_PASSWORD": "Admin@123#2026",
        "MCP_RDBMS_DATABASE": "mydb"
      }
    }
  }
}
```

#### 模式 A-2：全量连接串环境变量模式
```json
{
  "mcpServers": {
    "rdbms": {
      "command": "uvx",
      "args": ["atengk-mcp-server-rdbms"],
      "env": {
        "MCP_RDBMS_DB_URL": "postgresql+psycopg://user:password@localhost:5432/mydb"
      }
    }
  }
}
```

#### 模式 B：命令行参数直连模式
```json
{
  "mcpServers": {
    "rdbms": {
      "command": "uvx",
      "args": [
        "atengk-mcp-server-rdbms",
        "--db-url",
        "mysql+pymysql://root:Admin%40123@127.0.0.1:3306/mydb?charset=utf8mb4"
      ]
    }
  }
}
```

---

### 场景 2：单服务实例多数据库管理 (Single-Server Multi-DB)

适合希望由单个常驻服务统一管理多套业务数据库的场景。支持零物理配置文件的环境变量多库注入：

```json
{
  "mcpServers": {
    "rdbms_cluster": {
      "command": "uvx",
      "args": ["atengk-mcp-server-rdbms"],
      "env": {
        "MCP_RDBMS_DB_CRM": "postgresql+psycopg://user:pass@10.0.0.1:5432/crm_db",
        "MCP_RDBMS_DB_ERP": "mysql+pymysql://root:pass@10.0.0.2:3306/erp_db",
        "MCP_RDBMS_DEFAULT_DB": "crm",
        "MCP_RDBMS_ALLOW_DML": "true"
      }
    }
  }
}
```
* **大模型工作流**：客户端启动时读取 `rdbms://connections` 资源秒级获取连接列表；大模型调用工具时传入 `db="erp"` 即可精准跨库路由，缺省时自动路由到 `crm` 默认库。

---

### 场景 3：多服务实例独立挂载与自解释 (Multi-Server Instances)

适合在客户端配置中为不同业务系统分别挂载独立的 MCP 服务的场景。通过 `--server-name` 与 `--server-instructions` 为大模型注入业务身份：

```json
{
  "mcpServers": {
    "crm_database": {
      "command": "uvx",
      "args": [
        "atengk-mcp-server-rdbms",
        "--db-url", "postgresql+psycopg://user:pass@10.0.0.1:5432/crm",
        "--server-name", "crm-database-service",
        "--server-instructions", "企业 CRM 客户库专用通道。负责客户档案、跟进线索与商机表查询。"
      ]
    },
    "erp_database": {
      "command": "uvx",
      "args": [
        "atengk-mcp-server-rdbms",
        "--db-url", "mysql+pymysql://root:pass@10.0.0.2:3306/erp",
        "--server-name", "erp-database-service",
        "--server-instructions", "企业 ERP 进销存专用通道。负责采购入库、库存盘点与财务凭证表查询。"
      ]
    }
  }
}
```
* **大模型工作流**：在建联握手阶段，大模型通过专属名称与业务提示词直接分辨不同服务的定位，即使工具同名也能精准调度。

---

### 场景 4：远程服务调用 (HTTP/SSE 协议接入)

若服务已部署在局域网、云服务器或容器中，客户端可直接通过标准 HTTP SSE 端点接入：

```json
{
  "mcpServers": {
    "rdbms-remote": {
      "url": "http://<服务器IP>:8000/sse"
    }
  }
}
```

---

### 🌐 环境变量完整速查矩阵 (12-Factor App)

服务严格采用专属命名空间 `MCP_RDBMS_*`，杜绝通用无前缀变量以彻底消灭环境污染与串库风险：

| 分类 | 专属环境变量 (MCP_RDBMS_*) | 默认值 / 行为说明 |
| :--- | :--- | :--- |
| **完整连接** | `MCP_RDBMS_DB_URL` | 完整 RFC 1738 连接串（如 `sqlite:///:memory:`） |
| **零配置多库** | `MCP_RDBMS_DB_<ALIAS>` | 动态多库注入（如 `MCP_RDBMS_DB_DEV=...`、`MCP_RDBMS_DB_PROD=...`，免物理文件） |
| **默认数据库** | `MCP_RDBMS_DEFAULT_DB` | 多库环境下显式指定默认库别名（如 `dev`） |
| **多库配置文件** | `MCP_RDBMS_CONFIG` | 多数据源 YAML 配置文件绝对路径 |
| **数据库方言** | `MCP_RDBMS_DIALECT` | 数据库类型（`mysql`, `postgresql`, `oracle`, `mssql`, `sqlite` 等） |
| **主机地址** | `MCP_RDBMS_DB_HOST` | 数据库主机 IP 或域名（默认: `127.0.0.1`） |
| **端口** | `MCP_RDBMS_DB_PORT` | 数据库端口（缺省按方言自适应推导，如 MySQL 3306, PG 5432） |
| **用户名** | `MCP_RDBMS_USER` | 数据库登录用户 |
| **密码** | `MCP_RDBMS_PASSWORD` | **明文自动 URL 安全编码（如 `@` -> `%40`，彻底防踩坑）** |
| **数据库名称** | `MCP_RDBMS_DATABASE` | 目标数据库/Schema 库名 |
| **附加参数** | `MCP_RDBMS_PARAMS` | 连接查询参数（如 `charset=utf8mb4`） |
| **增删改权限** | `MCP_RDBMS_ALLOW_DML` | 宽容布尔值（`1`, `true`, `yes`, `on`, `t` 大小写不敏感） |
| **表结构变更** | `MCP_RDBMS_ALLOW_DDL` | 宽容布尔值（`1`, `true`, `yes`, `on`, `t` 大小写不敏感） |
| **通信传输协议** | `MCP_RDBMS_TRANSPORT` | `stdio`（默认）、`sse`、`streamable-http` |
| **服务监听地址** | `MCP_RDBMS_SERVER_HOST` | SSE/HTTP 监听地址（默认: `127.0.0.1`） |
| **服务监听端口** | `MCP_RDBMS_SERVER_PORT` | SSE/HTTP 监听端口（默认: `8000`） |
| **服务实例名称** | `MCP_RDBMS_SERVER_NAME` | 自定义服务实例名称（多实例挂载时区分业务，默认 `mcp-server-rdbms`） |
| **服务业务指令** | `MCP_RDBMS_SERVER_INSTRUCTIONS` | 面向大模型注入的专属业务提示词指令 |
| **审计日志路径** | `MCP_RDBMS_AUDIT_LOG_FILE` | 审计日志落盘路径（默认: `rdbms_mcp_audit.log`） |
| **审计记录范围** | `MCP_RDBMS_AUDIT_MODE` | 审计模式：`mutation`（仅变更, 默认）、`all`（含只读查询）、`off`（关闭） |
| **审计单片大小** | `MCP_RDBMS_AUDIT_MAX_BYTES` | 触发日志切片轮转的最大字节数（默认 10MB: `10485760`） |
| **审计保留份数** | `MCP_RDBMS_AUDIT_BACKUP_COUNT` | 保留的历史切片副本数（默认 `5`） |

> 📌 **解析优先级规则**：`命令行参数 (最高)` > `全量 URL 环境变量` > `独立字段环境变量拼装` > `标准内置默认值`。本地执行时会自动探测读取同级目录下的 `.env` 文件。

---

## 💡 智能体提示词与日常实战对话指南 (Prompt Recipes & Scenarios)

为让大模型在日常对话中更精准、更智能地调度数据库工具，推荐在各类 AI 客户端（**Cursor**、**Claude Desktop**、**Windsurf**、**Dify**）的系统提示词（System Prompt / Rules）中配置下方的**万能通用系统提示词**，并在日常工作中直接参考 **6 大高频实战提问剧场**。

---

### 1. 开箱即用万能系统提示词 (Universal System Prompt)

> 💡 **使用建议**：将以下内容直接复制到您的 AI 客户端系统提示词（System Prompt）、`.cursorrules` 或全局规则中。无论单库、多库、只读分析还是安全运维，一段提示词全面搞定：

```markdown
你是一名精通关系型数据库与 SQL 调优的高级数据专家与研发助理。当前环境已通过通用关系型数据库 MCP 服务接入数据源，请严格遵循以下日常交互准则：

1. 【库表摸底与多库路由】：
   - 对话初次涉及业务时，可通过只读资源 `rdbms://connections` 或 `db_info` 工具获取所有已配置连接别名与默认库状态；
   - 系统支持多库路由。若用户提问涉及指定库（如“在 CRM 库查…”），请在调用工具时显式传入 `db="crm"`；缺省时将自动路由至默认数据库。
2. 【安全只读探索与小样本采样】：
   - 探查业务宽表或未知数据时，请显式使用 `sql_query(sql=..., limit=3~5)` 进行微采样，确认实际列名与数据形态后再编写复杂统计分析；
   - 严禁盲目执行全量扫描；未显式指定 limit 时系统底层将安全截断至 100 行。
3. 【慢查询与执行计划诊断】：
   - 当用户要求“分析性能/优化慢查询/诊断索引”时，请调用 `sql_query(sql=..., explain=True)`；
   - 根据返回的执行计划（扫描类型、过滤条件、索引使用）为用户输出通俗、专业的性能诊断与建索引建议。
4. 【受控变更与破坏防御】：
   - 数据变更（DML）必须在单一事务中执行：`sql_dml(sql=...)`，单步失败自动全量回滚；系统 AST 会强制拦截无 WHERE 条件或恒真伪条件的误操作；
   - 结构变更（DDL）必须显式确认：调用 `sql_ddl(sql=..., confirm=True)`，调用前向用户清晰列出变更脚本并提示影响。
```

---

### 2. 日常高频自然语言实战剧场 (Daily Conversation Scenarios)

在日常使用中，您只需像与资深 DBA 对话一样提出自然语言需求，大模型即可精准触发对应工具：

#### 场景 1：日常摸库与表结构全息探查
* 👤 **您在聊天框说**：
  > “帮我看看当前数据库里有哪些和用户、权限相关的表？列出表名和注释，并把用户表的字段结构与索引详细查一下。”
* 🤖 **大模型背后的工具调用链路**：
  1. 调用 `schema_list_tables(pattern="*user*", include_views=True)` $\to$ 秒级筛选出 `sys_user`、`sys_user_role` 等业务表与表注释；
  2. 调用 `schema_describe_table(table_name="sys_user")` $\to$ 获取列类型、可空性、主键、外键与索引清单。
* 🎯 **大模型呈现给您的回答**：
  > 整理为清晰的 Markdown 结构表，为您详细解读 `sys_user` 的主键、关键业务列（如 `phone`、`status`）及现有唯一索引。

---

#### 场景 2：日常业务数据采样、统计聚合与分析
* 👤 **您在聊天框说**：
  > “统计一下今年第二季度各渠道的新增用户数和充值总额，按充值总额倒序排列，输出 Markdown 表格，并给出简要业务洞察。”
* 🤖 **大模型背后的工具调用链路**：
  1. 调用 `sql_query(sql="SELECT * FROM pay_order LIMIT 3")` $\to$ 采样确认订单表时间字段与金额字段类型；
  2. 调用 `sql_query(sql="SELECT channel, COUNT(DISTINCT user_id) AS new_users, SUM(amount) AS total_pay FROM pay_order WHERE created_at >= '2026-04-01' GROUP BY channel ORDER BY total_pay DESC")` $\to$ 安全聚合计算。
* 🎯 **大模型呈现给您的回答**：
  > 呈现整洁的格式化统计表格，并自动计算各渠道人均付费（ARPU）及业务洞察结论。

---

#### 场景 3：多数据库跨库联动查询与调度
* 👤 **您在聊天框说**：
  > “先在 CRM 库查出近 30 天消费排名前 5 的 VIP 客户列表，然后再去 ERP 库看看他们当前是否有未发货的订单。”
* 🤖 **大模型背后的工具调用链路**：
  1. 调用 `sql_query(db="crm", sql="SELECT customer_id, name, total_spent FROM vip_customer ORDER BY total_spent DESC LIMIT 5")` $\to$ 定向从 CRM 库提取 5 位客户；
  2. 调用 `sql_query(db="erp", sql="SELECT order_id, customer_id, status FROM erp_order WHERE customer_id IN (...) AND status = 'PENDING'")` $\to$ 定向从 ERP 库拉取未发货订单。
* 🎯 **大模型呈现给您的回答**：
  > 综合两套库的数据，为您汇总列出：“客户张总（CRM ID: 108）在 ERP 中有 2 笔待发货单（单号 #9021, #9045），请及时跟进履约。”

---

#### 场景 4：日常慢查询排查与索引性能调优
* 👤 **您在聊天框说**：
  > “这条订单查询语句在生产环境跑了 3 秒多：`SELECT * FROM orders WHERE status = 'PAID' AND user_id = 9527 ORDER BY create_time DESC`，帮我 explain 分析一下原因，看需要建什么索引？”
* 🤖 **大模型背后的工具调用链路**：
  - 调用 `sql_query(sql="SELECT * FROM orders WHERE status = 'PAID' AND user_id = 9527 ORDER BY create_time DESC", explain=True)` $\to$ 系统安全拦截并剥离危险修饰符，自动获取执行计划。
* 🎯 **大模型呈现给您的回答**：
  > “执行计划显示当前触发了全表扫描（`type: ALL`），预估扫描了 120 万行，且出现了内存排序（`Using filesort`）。**优化建议**：推荐建立联合索引 `CREATE INDEX idx_orders_user_status_time ON orders(user_id, status, create_time DESC);`，可将复杂度降至 `ref` 级别，消除 filesort。”

---

#### 场景 5：生产级受控数据修补与原子事务更新
* 👤 **您在聊天框说**：
  > “用户 2001 投诉扣款未到账，排查确认后需要把用户钱包余额增加 100 元，并将补单流水状态更新为已处理，这两步必须一起成功。”
* 🤖 **大模型背后的工具调用链路**：
  - 调用 `sql_dml(sql=["UPDATE user_wallet SET balance = balance + 100 WHERE user_id = 2001", "UPDATE pay_reconcile SET status = 'DONE' WHERE user_id = 2001 AND order_no = 'REC8891'"])` $\to$ 单一底层事务原子执行，若钱包更新失败则流水自动回滚，且 AST 强校验 WHERE 条件非空。
* 🎯 **大模型呈现给您的回答**：
  > “已成功在原子事务中执行 2 条更新语句，影响行数：2 行。随后已为您采样复核用户 2001 最新余额与流水状态，核验一致。”

---

#### 场景 6：原生方言运维探查与长事务诊断
* 👤 **您在聊天框说**：
  > “数据库好像有点卡，帮我看看当前 MySQL 实例有哪些运行时间超过 10 秒的活动连接或锁等待线程？”
* 🤖 **大模型背后的工具调用链路**：
  - 调用 `sql_query(sql="SELECT id, user, host, db, command, time, state, info FROM information_schema.processlist WHERE command != 'Sleep' AND time > 10 ORDER BY time DESC")` $\to$ 借助大模型内生方言能力直达运维视图。
* 🎯 **大模型呈现给您的回答**：
  > 迅速排查出线程 ID 为 8821 的报表导出慢查询正持有表行锁，并给出杀死阻塞线程的运维指引。

## 🐳 生产环境容器化常驻部署 (Docker & Docker Compose)

针对内网私有云、NAS（群晖/威联通）或 Linux 服务器，项目提供官方生产级 [`Dockerfile`](Dockerfile) 与 [`docker-compose.yaml`](docker-compose.yaml)，支持 **100% 环境变量无参启动**。

### 1. 使用 Docker Compose 一键拉起（推荐 ⭐⭐⭐⭐⭐）

在服务器上准备好 `docker-compose.yaml` 与 `connections.yaml`（或仅配置 `.env` 环境变量），直接启动常驻守护容器（**无需克隆代码仓库，直接从 GHCR 拉取预构建官方镜像**）：

```bash
# 启动常驻服务
docker compose up -d

# 查看运行日志与连接池状态
docker compose logs -f

# 停止服务
docker compose down
```

`docker-compose.yaml` 核心配置解析：
```yaml
services:
  mcp-rdbms:
    image: ghcr.io/atengk/mcp-server-rdbms:latest
    # image: ghcr.io/atengk/mcp-server-rdbms:1.1.4
    # build: .  # 开发者二次构建镜像时解开注释即可
    container_name: mcp-server-rdbms
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - MCP_RDBMS_TRANSPORT=sse
      - MCP_RDBMS_SERVER_HOST=0.0.0.0
      - MCP_RDBMS_SERVER_PORT=8000
      - MCP_RDBMS_CONFIG=/app/connections.yaml
    volumes:
      # 挂载多库配置（只读）
      - ./connections.yaml:/app/connections.yaml:ro
      # 挂载操作审计流水日志（宿主机持久化保存）
      - ./rdbms_mcp_audit.log:/app/rdbms_mcp_audit.log:rw
```

### 2. 使用 Docker CLI 独立运行

亦可直接使用标准 `docker run` 命令启动：

```bash
# 方式 A：挂载本地 connections.yaml 多库配置启动
docker run -d \
  --name mcp-rdbms \
  -p 8000:8000 \
  -v $(pwd)/connections.yaml:/app/connections.yaml:ro \
  -v $(pwd)/rdbms_mcp_audit.log:/app/rdbms_mcp_audit.log:rw \
  -e MCP_RDBMS_CONFIG=/app/connections.yaml \
  ghcr.io/atengk/mcp-server-rdbms:latest

# 方式 B：纯环境变量直连单数据库（免挂载任何文件，密码特殊字符自动免转义！）
docker run -d \
  --name mcp-rdbms \
  -p 8000:8000 \
  -e MCP_RDBMS_DIALECT=mysql \
  -e MCP_RDBMS_DB_HOST=192.168.1.100 \
  -e MCP_RDBMS_DB_PORT=3306 \
  -e MCP_RDBMS_USER=root \
  -e MCP_RDBMS_PASSWORD="Admin@123#2026" \
  -e MCP_RDBMS_DATABASE=mydb \
  ghcr.io/atengk/mcp-server-rdbms:latest
```

---

## 🌐 数据库连接串速查表与特殊字符转义避坑指南

SQLAlchemy 底层解析数据库连接串时采用标准 RFC 1738 URL 规范。**当密码中包含特殊字符时，如果不进行 URL 编码，解析器会将特殊字符误当作分隔符导致连接崩溃**。

### 1. 常见数据库标准连接串速查表

| 数据库类型 | 标准 Driver Scheme | 连接串格式示例 |
| :--- | :--- | :--- |
| **SQLite (文件库)** | `sqlite` | `sqlite:///./my_database.db`（相对路径）或 `sqlite:////data/db.sqlite`（绝对路径） |
| **SQLite (内存库)** | `sqlite` | `sqlite:///:memory:` |
| **PostgreSQL** | `postgresql+psycopg` | `postgresql+psycopg://user:password@127.0.0.1:5432/mydb?sslmode=prefer` |
| **MySQL 8.x / 5.7** | `mysql+pymysql` | `mysql+pymysql://user:password@127.0.0.1:3306/mydb?charset=utf8mb4` |
| **Oracle 19c / 21c** | `oracle+oracledb` | `oracle+oracledb://scott:tiger@192.168.1.10:1521/?service_name=orcl` |
| **SQL Server** | `mssql+pyodbc` | `mssql+pyodbc://sa:password@192.168.1.20:1433/mydb?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes` |
| **ClickHouse** | `clickhouse+connect` | `clickhouse+connect://default:password@127.0.0.1:8123/default` |

### 2. ⚠️ 核心避坑：密码特殊字符转义规则对照表

若您的密码中含有 `@`、`:`、`/`、`#` 等字符，请务必在连接串中转换为下表的 URL 编码：

| 特殊字符 | 误用场景痛点 | 必须转义为 (URL Encode) | 示例 (原始密码 -> 转义后连接串) |
| :---: | :--- | :---: | :--- |
| `@` | 会被误判定为主机名分隔符导致截断 | `%40` | `Admin@123` -> `user:Admin%40123@host:3306/db` |
| `:` | 会被误判定为端口分隔符 | `%3A` | `Pass:123` -> `user:Pass%3A123@host:3306/db` |
| `/` | 会被误判定为路径数据库名分隔符 | `%2F` | `P/ssword` -> `user:P%2Fssword@host:3306/db` |
| `#` | 会被误判定为 URL Hash 片段截断参数 | `%23` | `Pass#2024` -> `user:Pass%232024@host:3306/db` |
| `%` | URL 编码引导符自身 | `%25` | `P%ss` -> `user:P%25ss@host:3306/db` |

> 💡 **快速编码小妙招**：在终端执行 Python 单行命令即可安全获取转义密码：
> ```bash
> python -c "from urllib.parse import quote_plus; print(quote_plus('Admin@123#2026'))"
> # 输出: Admin%40123%232026
> ```
> 
> 🚀 **终极省心方案**：若使用上述 **原子字段环境变量模式**（如 `MCP_RDBMS_PASSWORD`），直接填入原始密码明文即可，服务启动时将自动完成 URL 安全编码，彻底避免因遗漏转义导致的崩溃！

---

## 📑 多数据库配置中心 `connections.yaml` 深度指南

当需要同时管理多个数据库时，可在本地创建 `connections.yaml` 文件（可参考根目录下提供的模板 [`connections.example.yaml`](connections.example.yaml)）：

```yaml
# 默认连接别名 (调用工具未传 db 参数时默认使用的连接)
default: "pg_main"

connections:
  # 1. 核心业务主库 (支持读写模式与事务)
  pg_main:
    url: "postgresql+psycopg://postgres:Admin%40123@10.0.0.1:5432/business_db"
    read_only: false       # 设为 false 配合 --allow-dml 允许修改
    is_default: true

  # 2. 只读离线数据仓库 (强制只读保护)
  mysql_analytics:
    url: "mysql+pymysql://reader:Public%40123@10.0.0.2:3306/dw_db?charset=utf8mb4"
    read_only: true        # 该连接强制只读，即使传入 --allow-dml 也禁止修改

  # 3. 本地嵌入式开发数据库
  sqlite_local:
    url: "sqlite:///./dev_cache.db"
    read_only: false
```

启动命令：
```bash
uvx atengk-mcp-server-rdbms --config ./connections.yaml --allow-dml
```

在大模型会话中，大模型可通过如下方式智能调度不同库：
- “查看默认库的所有表结构” -> 自动路由至 `pg_main`；
- “在 `mysql_analytics` 库上分析上周活跃用户数” -> 工具调用参数 `db="mysql_analytics"`。

---

## 🧩 扩展方言驱动支持与 `--with` 挂载

本服务默认内置了 SQLite、PostgreSQL、MySQL 驱动。若需连接 Oracle、SQL Server、ClickHouse 等其他数据库，推荐使用 `uvx` 的 `--with` 参数动态挂载，无需重新打包：

```bash
# 挂载 Oracle 驱动
uvx --with oracledb atengk-mcp-server-rdbms --db-url "oracle+oracledb://scott:tiger@host:1521/?service_name=orcl"

# 挂载 SQL Server 驱动
uvx --with pyodbc atengk-mcp-server-rdbms --db-url "mssql+pyodbc://sa:pass@host:1433/db?driver=ODBC+Driver+18+for+SQL+Server"

# 挂载 ClickHouse 驱动
uvx --with clickhouse-connect atengk-mcp-server-rdbms --db-url "clickhouse+connect://default:pass@host:8123/default"
```

若使用 `pip` 安装至现有虚拟环境，可安装对应的 extras 依赖包：
```bash
uv pip install "atengk-mcp-server-rdbms[oracle]"      # 安装 Oracle 支持
uv pip install "atengk-mcp-server-rdbms[mssql]"       # 安装 SQL Server 支持
uv pip install "atengk-mcp-server-rdbms[clickhouse]"  # 安装 ClickHouse 支持
uv pip install "atengk-mcp-server-rdbms[all]"         # 一键安装所有驱动扩展
```

---

## 💻 完整 CLI 启动参数参考表

```text
用法: atengk-mcp-server-rdbms [-h] [--version] [--doctor] [--format {text,json}]
                              [--server-name SERVER_NAME]
                              [--server-instructions SERVER_INSTRUCTIONS]
                              [--db-url DB_URL] [--config CONFIG]
                              [--allow-dml] [--allow-ddl]
                              [--transport {stdio,sse,streamable-http}]
                              [--host HOST] [--port PORT]
                              [--audit-log AUDIT_LOG]
                              [--audit-mode {mutation,all,off}]
                              [--audit-max-bytes AUDIT_MAX_BYTES]
                              [--audit-backup-count AUDIT_BACKUP_COUNT]
```

| 参数选项 | 类型 | 专属环境变量等价项 | 默认值 | 功能详细说明 |
| :--- | :---: | :---: | :---: | :--- |
| **`--doctor`** | `flag` | - | `False` | 启动运行环境、9 大方言驱动支持矩阵、专属命名空间与连接连通性全方位自检诊断探针 |
| **`--format`** | `str` | - | `text` | 配合 `--doctor` 使用的输出格式：`text`（终端 Rich 彩色卡片）或 `json`（机器可读标准 JSON） |
| **`--version`, `-v`** | `flag` | - | - | 显示服务版本、Python 运行时、SQLAlchemy 版本与操作系统架构基线并退出 |
| **`--server-name`** | `str` | `MCP_RDBMS_SERVER_NAME` | `mcp-server-rdbms` | 自定义当前 MCP 服务的显示名称，多服务独立挂载时供大模型精准识别业务归属 |
| **`--server-instructions`** | `str` | `MCP_RDBMS_SERVER_INSTRUCTIONS` | `None` | 面向大模型注入的专属业务指令，消除大模型在跨服务调度时的理解歧义 |
| **`--db-url`** | `str` | `MCP_RDBMS_DB_URL` | `None` | 单数据库连接串 URL，优先级高于环境变量 |
| **`--config`** | `str` | `MCP_RDBMS_CONFIG` | `None` | 多数据库 YAML 或 JSON 配置文件路径 |
| **`--allow-dml`** | `flag` | `MCP_RDBMS_ALLOW_DML` | `False` | 显式开启数据增删改（DML）权限门禁 |
| **`--allow-ddl`** | `flag` | `MCP_RDBMS_ALLOW_DDL` | `False` | 显式开启表结构变更（DDL）权限门禁 |
| **`--transport`** | `str` | `MCP_RDBMS_TRANSPORT` | `stdio` | 客户端通信协议，支持 `stdio`、`sse`、`streamable-http` |
| **`--host`** | `str` | `MCP_RDBMS_SERVER_HOST` | `127.0.0.1` | SSE 或 HTTP 服务的绑定监听地址 |
| **`--port`** | `int` | `MCP_RDBMS_SERVER_PORT` | `8000` | SSE 或 HTTP 服务的监听端口 |
| **`--audit-log`** | `str` | `MCP_RDBMS_AUDIT_LOG_FILE` | `rdbms_mcp_audit.log` | 审计日志落盘文件路径 |
| **`--audit-mode`** | `str` | `MCP_RDBMS_AUDIT_MODE` | `mutation` | 审计范围：`mutation`（仅 DML/DDL 变更）、`all`（全量含只读分析）、`off`（完全关闭） |
| **`--audit-max-bytes`** | `int` | `MCP_RDBMS_AUDIT_MAX_BYTES` | `10485760` (10MB) | 单文件触发日志切片轮转的最大字节数 |
| **`--audit-backup-count`** | `int` | `MCP_RDBMS_AUDIT_BACKUP_COUNT` | `5` | 本地保留的历史审计切片日志副本数量 |

---

## 🔒 生产级安全建议与分级合规审计

1. **默认强只读原则**：在生产环境中，如无明确数据修改需求，请勿传入 `--allow-dml` 与 `--allow-ddl`。默认模式下即使大模型生成恶意 SQL，也会在 AST 语法分析阶段被物理拦截并附带自愈重定向指引；
2. **连接密码脱敏保证**：大模型调用 `db_info` 或读取 `rdbms://connections` 资源探查网络拓扑时，所有连接凭据均强制替换为 `***`，彻底杜绝大模型在上下文回显或外部泄露凭据；
3. **专属命名空间隔离**：严格采用 `MCP_RDBMS_*` 命名空间，物理级过滤宿主机环境中的通用无前缀变量（如 `DATABASE_URL`），彻底消除跨进程环境污染与意外串库风险；
4. **分级操作审计与防爆截断 (`rdbms_mcp_audit.log`)**：
   - 服务支持三档分级审计模式：`mutation`（仅变更, 默认）、`all`（包含只读查询与 EXPLAIN）与 `off`（关闭）；
   - **审计防爆截断保护**：单条 SQL 超过 4096 字符或批量操作超过 100 条时自动智能折叠与截断，物理级防御磁盘被异常大日志打爆；
   - **切片安全轮转**：单文件达到 10MB 时自动切片轮转并保留最近 5 份历史归档；
   - **智能体自省资源**：大模型可通过标准 MCP 只读资源 `rdbms://audit/recent` 零 Tool Call 自主查阅最近执行的审计流水：
   ```json
   {
     "timestamp": "2026-10-14T08:30:00Z",
     "operation": "sql_dml",
     "db": "pg_main",
     "statements": ["UPDATE users SET status = 1 WHERE id = 100"],
     "status": "SUCCESS",
     "rows_affected": 1,
     "duration_ms": 12.5,
     "error": null
   }
   ```

---

## 📝 版本更新日志 (Changelog)

本项目采用 [git-cliff](https://github.com/orhun/git-cliff) 基于 Conventional Commits 提交历史全自动生成发版笔记，不维护静态的 `CHANGELOG.md` 物理文件。

所有历史版本的详细改动、新特性与修复记录，请直接访问 [GitHub Releases](https://github.com/atengk/mcp-server-rdbms/releases)。

---

## 🛡️ 社区规范与安全保障

本项目遵循现代工业级开源工程治理标准，致力于为开发者社区提供安全、透明、可信的软件供应链环境：

| 规范维度 | 说明与指引文档 | 核心原则 |
| :--- | :--- | :--- |
| **🤝 参与贡献** | [CONTRIBUTING.md](./CONTRIBUTING.md) | 遵循 GitHub Flow 与 Conventional Commits 提交规范 |
| **📜 行为准则** | [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) | 遵循 Contributor Covenant 2.1，营造开放包容的协作氛围 |
| **🔒 安全策略** | [SECURITY.md](./SECURITY.md) | 负责任漏洞披露 (Responsible Disclosure)，48 小时响应闭环 |
| **📄 开源许可** | [LICENSE](./LICENSE) / [NOTICE](./NOTICE) | 基于 Apache 2.0 协议开源，包含专利防卫与商标保护，欢迎自由商业与个人使用 |

