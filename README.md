# atengk-mcp-server-rdbms

<p align="center">
  <a href="https://pypi.org/project/atengk-mcp-server-rdbms/"><img src="https://img.shields.io/pypi/v/atengk-mcp-server-rdbms.svg?color=blue&label=PyPI" alt="PyPI version"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/releases"><img src="https://img.shields.io/github/v/release/atengk/mcp-server-rdbms?style=flat-square&color=blue&label=Release" alt="GitHub Release"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/atengk/mcp-server-rdbms/ci.yml?branch=main&label=CI&style=flat-square" alt="CI Status"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License"></a>
  <a href="https://github.com/atengk/mcp-server-rdbms/actions"><img src="https://img.shields.io/badge/tests-187%20passed-brightgreen.svg?style=flat-square" alt="Tests"></a>
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

    subgraph ProtocolLayer ["通信传输与分层环境层"]
        FastMCP["FastMCP 协议服务器 (stdio / sse)"]
        Env["分层环境解析器 (core/env.py)"]
        Dotenv[".env 自动探测与 RFC 1738 密码免转义拼装"]
    end

    subgraph GuardLayer ["AST 深度语法安全守卫 (core/guard.py)"]
        ASTParse["sqlglot AST 语法树解析与分析"]
        ReadOnly["只读语义校验 (Select / CTE With)"]
        LimitInject["自动注入安全 LIMIT 截断 (默认 100 行)"]
        WhereGuard["DML 强制阻断无 WHERE 条件的 UPDATE/DELETE"]
        ExplainGuard["sql_query explain 危险修饰符 (ANALYZE) 拦截与剥离"]
    end

    subgraph EngineLayer ["连接池与多库路由中枢 (core/connection.py)"]
        Registry["ConnectionRegistry (多库配置中心)"]
        Pool["连接池健康预检与自愈 (pool_pre_ping)"]
        Audit["独立审计流水日志 (rdbms_mcp_audit.log)"]
    end

    subgraph DatabaseLayer ["多元关系型数据库集群 (SQLAlchemy 2.0)"]
        MySQL[("MySQL 8.x / 5.7 / MariaDB")]
        PostgreSQL[("PostgreSQL 12~17")]
        SQLite[("SQLite 内存库 / 本地文件库")]
        Oracle[("Oracle 19c / 21c")]
        MSSQL[("SQL Server / ClickHouse / 国产库")]
    end

    Client -->|"JSON-RPC (stdio / sse)"| FastMCP
    Dotenv --> Env --> Registry
    FastMCP -->|"6 核心工具调用"| GuardLayer
    GuardLayer -->|"AST 验证通过"| Registry
    Registry --> Pool
    Pool -->|"工作线程池异步卸载 (anyio)"| DatabaseLayer
    Registry -.->|"写操作流水异步落盘"| Audit
```

- 🚀 **通用多数据库抽象底座**：
  - 基于 SQLAlchemy 2.0 驱动引擎，默认内置 **SQLite**、**PostgreSQL** (`psycopg3`)、**MySQL** (`pymysql`)；
  - 插件化扩展无缝支持 **Oracle**、**SQL Server**、**ClickHouse** 及各类符合标准方言的国产数据库（达梦、人大金仓等）。
- 🛡️ **AST 语法树级深度安全守卫 (Guardrail)**：
  - 基于 `sqlglot` 语法树静态分析，只读模式下物理拦截任何多语句拼接（SQL 注入防御）以及非 SELECT/WITH 写入操作；
  - **自动 LIMIT 注入**：为未指定行数的大模型查询强制追加安全截断（默认 100 行），彻底杜绝全表拉取导致 OOM 或上下文爆炸；
  - **灾难性误改误删阻断**：静态分析强制拦截缺少 `WHERE` 条件的 `UPDATE` 与 `DELETE` 语句，直接驳回。
- ⚡ **原子事务与权限双重门禁**：
  - `sql_dml` 接受单条或批量 SQL，底层在**单一原子事务块**中执行，任何单步失败全量自动 `ROLLBACK`，绝不留脏数据；
  - 默认强只读保护，写权限必须通过 `--allow-dml` 与 `--allow-ddl` 显式授权，且 DDL 建表/删表要求 `confirm=True` 二次确认。
- 🌐 **多数据库配置中心与连接池自愈**：
  - 支持单库环境变量/CLI 直连，亦支持通过 YAML/JSON 配置文件声明多库路由；
  - 连接池集成 `pool_pre_ping=True` 探针预检与周期回收，毫秒级自愈因外部超时、防火墙丢包或数据库重启导致的死连接。
- 🔍 **精炼 6 核心工具矩阵**：无二义性、零冗余设计，工具严格按领域命名空间规范组织，模型理解与调用准确率极高。
- 📝 **变更操作独立审计流水**：所有 DDL 与 DML 操作均异步落盘记录至本地 `rdbms_mcp_audit.log`，包含时间戳、执行 SQL、影响行数与耗时。

---

## 🛠️ 6 核心工具矩阵全景契约

所有工具均支持可选的 `db` 参数。不传时自动路由到默认连接；传入时精确定位目标多库别名：

| 领域前缀 | 工具名称 | 参数契约 | 功能描述与安全约束 |
| :--- | :--- | :--- | :--- |
| **`db_`** | `db_info` | `(db: str = None)` | 一站式探查数据库内核版本、当前 Schema/用户、只读保护及全部已配置连接别名列表（密码强制 `***` 掩码脱敏） |
| **`schema_`** | `schema_list_tables` | `(schema=None, pattern=None, include_views=False, include_foreign_keys=False, db=None)` | 获取业务数据表与视图清单、表注释并支持模式过滤与可选外键依赖拓扑分析。自动过滤数据库系统保留模式 |
| | `schema_describe_table` | `(table_name: str, schema=None, db=None)` | 一站式全息探查数据表列明细（类型、可空性、默认值）、主键约束、外键关联与全部索引明细 |
| **`sql_`** | `sql_query` | `(sql: str, limit: int = 100, format="json", explain: bool = False, db=None)` | 安全只读数据采样与业务分析，支持复杂 CTE `WITH` 语法。支持 `json` / `markdown` / `csv` 格式、自动截断长文本并注入 LIMIT；`explain=True` 时内生获取执行计划 |
| | `sql_dml` | `(sql: str \| list[str], db=None)` | 原子事务数据增删改（支持单条或批量）。**单步失败全量自动回滚**，受 `--allow-dml` 门禁管控，**强制拦截无 WHERE 条件操作** |
| | `sql_ddl` | `(sql: str, confirm: bool = False, db=None)` | 结构定义变更（建表、删表、改表）。受 `--allow-ddl` 权限管控并要求 `confirm=True` 二次确认 |

---

## 📚 MCP 只读资源 (Resources) 契约

服务全面接入标准 MCP Resources 协议，为支持资源挂载的 AI 客户端（如 Claude Desktop、Cursor 等）提供零 Tool Call 秒级注入数据库上下文能力：

| 资源 URI / 模板 | 类型 | 传输格式 | 功能说明与容灾表现 |
| :--- | :--- | :--- | :--- |
| `rdbms://connections` | 静态资源 | `application/json` | 输出当前所有已配置数据库连接别名、方言内核、默认库标记与只读状态（密码强制 `***` 掩码脱敏） |
| `rdbms://{db}/schema` | 动态模板 | `application/json` | 按需获取指定连接的数据库模式名、业务表与视图清单概要及注释。当目标连接不可达或配置不存在时优雅降级返回 `status: "error"` 与错误原因，不导致协议崩溃 |

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

## 🔌 MCP 客户端通用标准配置

> 💡 **提示**：以下配置完全遵循 Model Context Protocol (MCP) 官方开放规范，适用于 **Claude Desktop**、**Cursor**、**Windsurf**、**VS Code** 以及任何兼容 MCP 协议的 AI 客户端。

### 场景 1：标准本地调用 (stdio 协议，推荐)

在您所使用客户端的 MCP 配置文件（如 `mcp.json` 或 `claude_desktop_config.json`）的 `"mcpServers"` 块中添加。支持**环境变量注入**与**命令行参数**两种等价范式：

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

#### 模式 C：多数据库配置中心模式
```json
{
  "mcpServers": {
    "rdbms": {
      "command": "uvx",
      "args": ["atengk-mcp-server-rdbms"],
      "env": {
        "MCP_RDBMS_CONFIG": "/path/to/connections.yaml",
        "MCP_RDBMS_ALLOW_DML": "true",
        "MCP_RDBMS_ALLOW_DDL": "true"
      }
    }
  }
}
```

---

### 🌐 环境变量完整速查矩阵 (12-Factor App)

服务提供官方推荐前缀 `MCP_RDBMS_*` 与通用标准环境变量双重支持：

| 分类 | 推荐主环境变量 | 宽容兼容变量 | 默认值 / 行为说明 |
| :--- | :--- | :--- | :--- |
| **完整连接** | `MCP_RDBMS_DB_URL` | `DATABASE_URL` | 完整 RFC 1738 连接串（如 `sqlite:///:memory:`） |
| **多库配置** | `MCP_RDBMS_CONFIG` | `CONFIG_FILE` | 多数据源 YAML 配置文件绝对路径 |
| **数据库方言** | `MCP_RDBMS_DIALECT` | `DB_DIALECT` | 数据库类型（`mysql`, `postgresql`, `oracle`, `mssql`, `sqlite` 等） |
| **主机地址** | `MCP_RDBMS_DB_HOST` | `DB_HOST` | 数据库主机 IP 或域名（默认: `127.0.0.1`） |
| **端口** | `MCP_RDBMS_DB_PORT` | `DB_PORT` | 数据库端口（缺省按方言自适应推导，如 MySQL 3306, PG 5432） |
| **用户名** | `MCP_RDBMS_USER` | `DB_USER` / `DB_USERNAME` | 数据库登录用户 |
| **密码** | `MCP_RDBMS_PASSWORD` | `DB_PASSWORD` / `DB_PASS` | **明文自动 URL 安全编码（如 `@` -> `%40`，彻底防踩坑）** |
| **数据库名称** | `MCP_RDBMS_DATABASE` | `DB_NAME` / `DB_DATABASE` | 目标数据库/Schema 库名 |
| **附加参数** | `MCP_RDBMS_PARAMS` | `DB_PARAMS` | 连接查询参数（如 `charset=utf8mb4`） |
| **增删改权限** | `MCP_RDBMS_ALLOW_DML`| `MCP_ALLOW_DML` | 宽容布尔值（`1`, `true`, `yes`, `on`, `t` 大小写不敏感） |
| **表结构变更** | `MCP_RDBMS_ALLOW_DDL`| `MCP_ALLOW_DDL` | 宽容布尔值（`1`, `true`, `yes`, `on`, `t` 大小写不敏感） |
| **通信传输协议** | `MCP_RDBMS_TRANSPORT`| `MCP_TRANSPORT` | `stdio`（默认）、`sse`、`streamable-http` |
| **服务监听地址** | `MCP_RDBMS_SERVER_HOST` | `HOST` | SSE/HTTP 监听地址（默认: `127.0.0.1`） |
| **服务监听端口** | `MCP_RDBMS_SERVER_PORT` | `PORT` | SSE/HTTP 监听端口（默认: `8000`） |

> 📌 **解析优先级规则**：`命令行参数 (最高)` > `全量 URL 环境变量` > `独立字段环境变量拼装` > `标准内置默认值`。本地执行时会自动探测读取同级目录下的 `.env` 文件。

---

### 场景 2：远程服务调用 (SSE 协议客户端接入)

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

## 💡 智能体提示词模版与实战指南 (Agent Prompt Recipes)

为充分发挥大模型内生 SQL 能力与零 Tool Call 极速交互优势，推荐在各类 AI 客户端（如 **Claude Desktop**、**Cursor**、**Windsurf**、**Dify**）的系统提示词（System Prompt）或项目规则中按需选用以下经过实战检验的高效模版：

### 模版 1：零 Tool Call 预装载全局数据库上下文 (Zero-Tool Context Preloading)
> **适用场景**：对话启动瞬间即掌握全库连接拓扑与表清单，彻底免去每次提问大模型先调用 `db_info` 或 `schema_list_tables` 查表的往返开销与 Token 浪费。

```markdown
你是一个精通关系型数据库的专业资深工程师与数据专家。
当前环境已接入通用数据库 MCP 服务，请遵循以下上下文约束：
1. 【全局连接认知】：优先通过 MCP 静态资源 `rdbms://connections` 获取当前系统注册的所有可用数据库连接别名、方言内核与默认只读属性；
2. 【表清单与模式背景】：通过 MCP 动态资源模板 `rdbms://{db}/schema` 直接预置目标数据库的模式名、业务数据表及表注释概要；
3. 【直达业务查询】：用户提出业务数据分析、采样或统计需求时，请直接基于已知表结构编写精确的只读 SQL 并通过 `sql_query` 执行；除非需要精细到某一列的深度类型与索引分析（调用 `schema_describe_table`），严禁盲目发起全库表清单扫描！
```

---

### 模版 2：数据智能分析与慢查询诊断专家 (Data Analyst & Tuning Assistant)
> **适用场景**：日常业务数据采样、多维统计聚合、报表生成，以及复杂慢查询与索引命中瓶颈排查。

```markdown
你是一名高级数据库性能调优与只读数据分析专家。
在协助用户进行数据查询与性能诊断时，请严格执行以下规范：
1. 【只读安全规范】：仅使用 `sql_query` 工具。未指定 LIMIT 的数据采样，系统底层会自动注入安全截断限制（默认 100 行）；
2. 【大模型内生能力】：需要探查数据库活动进程、长事务会话或原生建表 DDL 时，无需寻找专有工具，请直接根据当前方言自主构造标准只读 SQL（例如 PostgreSQL 查询 `pg_stat_activity`，MySQL 执行 `SHOW PROCESSLIST` 或 `SHOW CREATE TABLE`），借助 `sql_query` 自由探查；
3. 【执行计划深度诊断】：当用户要求“分析该查询性能/诊断慢查询/排查索引命中”时，请调用 `sql_query(sql=..., explain=True)`。系统会自动剥离 ANALYZE 危险修饰符以守牢安全底线；请结合返回的扫描类型（如 ALL/Index/Seq Scan）、预估行数与索引键，为用户输出通俗易懂的调优诊断报告与索引优化建议。
```

---

### 模版 3：生产级安全受控变更工程师 (Safe Migration & Atomic Mutation)
> **适用场景**：数据修补、结构迁移、批量更正或紧急运维维护，守牢不可逆破坏防御红线。

```markdown
你是一名严谨的数据库运维变更专家。
当前会话已开放受控写入权限，但在执行任何数据（DML）或结构（DDL）操作前，必须严格遵循以下铁律：
1. 【灾难性误改误删物理拦截】：严禁执行任何缺少 WHERE 条件的 UPDATE 或 DELETE；任何诸如 `WHERE 1=1` 的恒真伪条件均会被系统 AST 守卫直接强行驳回！
2. 【原子性事务保障】：多条关联数据更新请合并为 SQL 列表传入 `sql_dml(sql=[...])`。系统会在单一底层事务中原子执行，任一语句报错将全量自动回滚；
3. 【结构变更二次确认】：执行表结构定义变更时，必须使用 `sql_ddl(sql=..., confirm=True)`。在正式调用前，向用户完整展示预期执行的 DDL 脚本并说明影响范围；
4. 【变更自检闭环】：每次数据变更完成后，主动调用 `sql_query` 采样受影响行并向用户核验数据一致性。
```

---

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
用法: atengk-mcp-server-rdbms [-h] [--db-url DB_URL] [--config CONFIG] [--allow-dml]
                              [--allow-ddl] [--transport {stdio,sse,streamable-http}]
                              [--host HOST] [--port PORT]
```

| 参数选项 | 类型 | 环境变量等价项 | 默认值 | 功能详细说明 |
| :--- | :---: | :---: | :---: | :--- |
| **`--db-url`** | `str` | `DATABASE_URL` | `None` | 单数据库连接串 URL，优先级高于环境变量 |
| **`--config`** | `str` | `MCP_RDBMS_CONFIG` | `None` | 多数据库 YAML 或 JSON 配置文件路径 |
| **`--allow-dml`** | `flag` | - | `False` | 显式开启数据增删改（DML）权限门禁 |
| **`--allow-ddl`** | `flag` | - | `False` | 显式开启结构变更（DDL）权限门禁 |
| **`--transport`** | `str` | - | `stdio` | 客户端通信协议，支持 `stdio`、`sse`、`streamable-http` |
| **`--host`** | `str` | - | `127.0.0.1` | SSE 或 HTTP 服务的绑定监听地址 |
| **`--port`** | `int` | - | `8000` | SSE 或 HTTP 服务的监听端口 |

---

## 🔒 生产级安全建议与合规审计

1. **默认强只读原则**：在生产环境中，如无明确数据修改需求，请勿传入 `--allow-dml` 与 `--allow-ddl`。默认模式下即使大模型生成恶意 SQL，也会在 AST 语法分析阶段被物理拦截；
2. **连接密码脱敏保证**：大模型调用 `db_info` 探查网络拓扑时，所有连接凭据均强制替换为 `***`，杜绝大模型在上下文回显或外部泄露凭据；
3. **审计追溯 (`rdbms_mcp_audit.log`)**：服务自动在运行目录下生成并维护 `rdbms_mcp_audit.log` 审计流水文件，每一行均以格式化 JSON 记录操作状态：
   ```json
   {"timestamp":"2026-10-04T08:30:00Z","operation":"sql_dml","db":"pg_main","statements":["UPDATE users SET status = 1 WHERE id = 100"],"status":"SUCCESS","rows_affected":1,"duration_ms":12.5,"error":null}
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
| **📄 开源许可** | [LICENSE](./LICENSE) | 基于 MIT 协议开源，欢迎自由使用、扩展与集成 |

