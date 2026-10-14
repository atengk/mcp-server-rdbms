# 0026: 多数据库路由引导与服务元数据自解释体系

- **状态**: Accepted
- **日期**: 2026-10-14
- **决定者**: 阿腾 (Ateng)

## 背景与痛点

在企业级部署与多业务库协同场景下，大模型在使用 MCP 数据库服务时常面临多库识别与定向调度的歧义问题，具体表现为两类形态：

1. **单服务实例多库场景 (Single-Server Multi-DB)**：
   服务内部通过 `MCP_RDBMS_DB_<ALIAS>` 挂载了多个库（如 CRM 与 ERP），尽管各核心工具底层已具备 `db` 参数，但缺乏面向大模型的显式提示词引导，部分参数量较小的大模型容易忽略 `db` 参数而发生漏传或幻觉，导致误在默认库上执行了非预期操作；
2. **多服务实例独立挂载场景 (Multi-Server Instances)**：
   用户在 MCP 客户端（如 Claude Desktop、Cursor、Cherry Studio 等）中为不同数据库配置了多个独立的 `mcp-server-rdbms` 进程。先前实现中服务的名称硬编码为 `mcp-server-rdbms`，系统提示词 `instructions` 亦为通用固定文本。在大模型同时挂载多个数据库服务时，对话上下文出现多套同名工具，大模型无法精准获知哪组工具对应哪套业务数据库。

## 架构决策

经 Grilling 访谈与领域推演，决定实施**双层融合多库解耦策略**：

1. **服务元数据自解释 (Server Metadata Self-Explanation)**：
   - 扩展 `ServerRuntimeConfig` 契约，新增 `server_name`（默认 `mcp-server-rdbms`）与 `server_instructions` 字段；
   - 遵循 `Dedicated Namespace Rule`，新增环境变量映射：
     - `MCP_RDBMS_SERVER_NAME` / CLI `--server-name`：允许用户自定义当前服务实例显示名称（例如 `crm-database-mcp`）；
     - `MCP_RDBMS_SERVER_INSTRUCTIONS` / CLI `--server-instructions`：允许用户为大模型定制专属服务系统指令（例如 `负责全量 CRM 客户关系管理数据库的查询与操作`）；
   - 在 `create_server` 装配时将上述定制元数据注入 `MCPServer(name=..., instructions=...)`，使大模型在 MCP 建联握手时秒级明确该服务的业务定位。
2. **六核心工具多库路由强化引导 (Multi-DB Routing Guidance)**：
   - 坚守“精炼 6 核心工具契约”的架构不变量，不随意破坏或增殖工具；
   - 系统化微调 6 核心工具（`db_info`, `schema_list_tables`, `schema_describe_table`, `sql_query`, `sql_dml`, `sql_ddl`）的 `description` 与参数文档，统一嵌入明确的多库路由指引：
     > “支持多数据库路由，可通过 db_info 工具或 rdbms://connections 资源获取已配置连接别名列表；跨库操作时请显式指定 db='<alias>'，缺省时将自动路由至默认数据库。”
   - 显著降低小模型在多库环境下的漏传率与跨库幻觉。

## 效果与收益

- **认知零歧义**：多实例挂载时大模型可通过服务名称与自定义 Instructions 瞬间定位业务边界；
- **自愈路由闭环**：单实例多库场景下大模型受工具描述清晰引导，自主识别 `db` 参数并与 `rdbms://connections` 资源形成感知与执行闭环；
- **全向下兼容**：单库默认场景下无需额外参数配置，体验无缝丝滑。
