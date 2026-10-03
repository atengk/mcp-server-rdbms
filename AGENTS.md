# mcp-server-rdbms 智能体工程指导规约 (AGENTS.md)

本文件是后续参与本项目开发、维护与演进的 AI Agent 必须严格遵循的工程指引与核心不变量（Invariants）。

---

## 1. 项目定位与核心心智模型

`mcp-server-rdbms` 是基于 Python、FastMCP 与 SQLAlchemy 2.0 构建的通用关系型数据库 MCP 服务。

### 架构四维角色与分工
1. **协议接入与装配 (`server.py`)**：负责 FastMCP 实例创建、CLI 参数解析与 8 核心工具挂载，保持轻薄。
2. **核心基础设施 (`core/`)**：
   - `connection.py`：连接池与多库配置中心 (`ConnectionRegistry`)。
   - `guard.py`：基于 `sqlglot` 的 AST 语法树安全分析、只读校验与自动 `LIMIT` 重写注入。
   - `dialect.py`：方言识别与缺失驱动智能拦截提示 (`DialectRegistry`)。
   - `audit.py`：写操作独立审计流水记录器 (`rdbms_mcp_audit.log`)。
3. **领域工具实现 (`tools/`)**：严格按领域前缀隔离（`db_` / `schema_` / `sql_` / `admin_`）。
4. **模型与契约 (`models/` 或 `config.py`)**：配置数据结构与结果载荷定义。

---

## 2. 不可违背的核心不变量 (Core Invariants)

在编写任何代码与重构时，以下 6 条规则是最高安全与架构底线：

1. **异步事件循环防阻塞 (Offload Rule)**：
   - FastMCP 运行在异步事件循环中，而 SQLAlchemy 引擎采用标准同步模式。
   - 所有数据库 I/O 操作**必须**通过 `anyio.to_thread.run_sync` 卸载至工作线程池执行，严禁在异步工具函数中直接进行同步阻塞 I/O。
2. **AST 零绕过只读防御 (Guardrail Rule)**：
   - `sql_query` 在下发到数据库前，**必须**先由 `core/guard.py` 完整解析为 `sqlglot` AST。
   - 验证所有表达式为只读操作（允许并深度解析 `WITH ... SELECT` CTE 语法）；
   - 若查询未包含 `LIMIT`，强制注入安全截断限制；
   - 严禁拼接多语句（防注入）。
3. **默认只读与写权限隔离 (Default Read-Only Rule)**：
   - 默认禁止执行任何 DML 或 DDL。
   - 仅当启动配置显式激活 `--allow-dml` / `--allow-ddl` 时，对应工具才允许执行；否则一律返回友好权限拒绝提示。
4. **DML 原子事务与破坏防御 (Atomic & Transactional Rule)**：
   - `sql_dml` 接受单条或列表批量 SQL，**必须**在单一事务块中执行，任何一条语句失败必须全量自动 `ROLLBACK`。
   - 静态 AST 检测**强制拦截**无 `WHERE` 条件的 `UPDATE` 与 `DELETE` 语句，直接驳回。
5. **变更独立审计落盘 (Audit Trail Rule)**：
   - 任何 `sql_dml` 与 `sql_ddl` 执行，无论成功或抛出异常，均需通过 `core/audit.py` 写入本地 `rdbms_mcp_audit.log`。
6. **缺失驱动友好拦截 (Fail-Friendly Rule)**：
   - 当遇到用户配置了未安装驱动的连接串（如 `oracle+oracledb://...`）触发 `NoSuchModuleError` 时，**严禁**直接暴露底层丑陋堆栈。
   - 必须通过 `DialectRegistry` 捕获并输出结构化提示，明确告知用户执行 `uv pip install "mcp-server-rdbms[dialect]"` 安装对应扩展。

---

## 3. 精炼 8 核心工具契约

项目中仅维护以下 8 个高内聚工具，严禁随意扩散或新增重叠冗余工具：

| 工具名称 | 领域归属 | 核心职责 | 关键安全要求 |
| :--- | :--- | :--- | :--- |
| `db_get_info` | `db_` | 获取方言内核、版本、当前 Schema 与用户 | 只读探查 |
| `schema_list_tables` | `schema_` | 表/视图清单、注释与外键拓扑关系 | 只读探查，聚合外键关联 |
| `schema_describe_table` | `schema_` | 列明细、类型、可空性、主键、外键与索引 | 一站式返回全部表元数据 |
| `sql_query` | `sql_` | 样本预览、数据采样与安全只读分析 | AST 强制只读校验 + 自动 LIMIT |
| `sql_explain` | `sql_` | 获取执行计划以分析慢查询 | 仅允许执行 EXPLAIN 语句 |
| `sql_dml` | `sql_` | 数据增删改（支持单条/批量） | `--allow-dml` 门禁 + 原子事务 + 禁无 WHERE |
| `sql_ddl` | `sql_` | 表结构定义变更（建表/删表/改表） | `--allow-ddl` 门禁 + 显式确认 |
| `admin_list_running_queries` | `admin_` | 观测活动进程与长查询 | 只读观测，对 SQLite 等库优雅降级 |

---

## 4. 代码风格与工程规范

### 4.1 注释规范
新建 Python 模块与类时，必须在顶部添加标准 Docstring：
```python
"""
mcp-server-rdbms: 模块核心职责说明.

@author Ateng
@since 2026-10-03
"""
```

### 4.2 类型提示与防御性编程
- 全面使用 Python 3.12 原生类型注解（如 `list[str]`、`dict[str, Any]`、`str | None`），严禁使用无类型标记的裸变量。
- 查询结果列表返回约定：查询无结果时**统一返回空列表 `[]`**，严禁返回 `None`。
- 异常处理：禁止吞异常（空 `except` 块）；底层异常需转换为语义明确的 `RdbmsMcpError` 或结构化错误信息。

### 4.3 变更最小化
- 修改存量代码时严格遵循最小变更原则，严禁对无关文件进行全量无意义格式化重排。

---

## 5. 测试与快速验证循环 (Tight Test Loop)

1. **测试基础设施**：
   - 单元测试统一使用 pytest，测试套件位于 `tests/` 目录。
   - 所有数据库测试优先使用 SQLite 内存库（`sqlite:///:memory:`）作为测试基座，确保单测零网络依赖且毫秒级完成。
2. **测试优先级**：
   - 核心首测 `tests/test_guard.py`：测试各种 SQL（只读、CTE、注入、多语句、无 WHERE 的 UPDATE/DELETE）的 AST 校验与注入；
   - 其次测试 `tests/test_connection.py`：多库路由与缺失驱动智能指引；
   - 最后测试 `tests/test_tools.py`：FastMCP 8 核心工具端到端调用。
3. **日常验证命令**：
   ```powershell
   # 运行完整单元测试
   uv run pytest

   # 代码风格与静态类型检查
   uv run ruff check
   ```

---

## 6. Git 提交与版本管理纪律

- **严禁自主静默提交**：日常代码修改停留在工作区供审阅；只有在用户明确下达“提交/commit”指令时，方可执行提交。
- **精准暂存**：严禁 `git add .` 或 `git add -A`，必须显式指定目标文件路径。
- **提交信息规范**：遵循 Conventional Commits 格式 `<type>(<scope>): <中文描述>`，例如：
  - `feat(guard): 实现基于 sqlglot 的 AST 只读语法树校验与 LIMIT 注入`
  - `fix(connection): 优化缺少数据库驱动时的友好错误拦截提示`

---

## 7. 智能体工程技能体系 (Agent skills)

### Issue tracker

本仓库的工单与需求规范通过 `gh` CLI 统一在 GitHub Issues 中追踪。参见 `docs/agents/issue-tracker.md`。

### Triage labels

采用五大经典角色分诊标签体系。参见 `docs/agents/triage-labels.md`。

### Domain docs

采用单上下文文档布局（根目录 `CONTEXT.md` 与 `docs/adr/`）。参见 `docs/agents/domain.md`。
