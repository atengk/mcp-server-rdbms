# 0022: 自愈型意图防护、采样保护与纯环境变量多库治理

- **状态**: Accepted
- **日期**: 2026-10-14
- **决定者**: 阿腾 (Ateng)

## 背景与痛点

在基于真实智能体（Claude Desktop、Cursor、Windsurf 等）与复杂多库环境的交互实践中，系统暴露出以下 4 大核心使用体验痛点：

1. **写操作误入只读通道的冷冰冰拒绝**：LLM 常常具备“只读直觉”，在下发数据修改语句（`UPDATE/INSERT/DELETE/MERGE`）或表结构变更语句时，下意识调用默认的 `sql_query`。原有 AST 安全守卫仅简单抛出“禁止修改”错误，缺乏明确的下一跳建议，导致 LLM 在多轮会话中迷茫、道歉甚至放弃重试；
2. **宽表采样时的上下文挤占**：面对 30+ 字段的业务宽表，默认安全截断（100 行）仍可能产生数万字符载荷，冲垮模型上下文，且模型无法从返回结果中直接感知是否触及了行数上限；
3. **零物理文件多环境多库配置缺失**：容器（Docker/K8s）及客户端 MCP 配置（如 `claude_desktop_config.json` 的 `env` 节点）强烈倾向于零本地磁盘文件依赖。此前多库仅支持物理 YAML 文件，无法直接通过环境变量声明多个不同数据库连接；
4. **多库未指定连接时的防呆体验**：在多连接环境下，若 LLM 遗漏了 `db` 参数且无默认库，原有报错缺乏对当前已注册可用连接的直观透出以及对 MCP 只读资源 `rdbms://connections` 的引导。

## 架构决策

为解决上述痛点，实施以下四项架构与体验增强：

1. **自愈型智能重定向拦截 (Self-Healing Remediation)**：
   - 当 `sql_query` AST 深度扫描捕获到 DML 节点（`Insert` / `Update` / `Delete` / `Merge`）时，错误提示直接附带下一跳自愈指引：“💡 自愈指引：sql_query 仅支持只读分析；若需执行数据变更，请在开启 `--allow-dml` 权限后改用 `sql_dml` 工具下发变更”；
   - 当捕获到 DDL 节点（`Create` / `Alter` / `Drop` / `TruncateTable`）时，精准指引改用 `sql_ddl`（需开启 `--allow-ddl` 且传 `confirm=True`）。
2. **微采样心智引导与结果集截断元数据 (Micro-Sampling & Truncation Metadata)**：
   - 在 `sql_query` 工具描述中注入高优先级采样建议：“在探索未知业务表时，强烈建议显式指定 `limit=3~5` 获取结构样例；未指定时默认截断至 100 行”；
   - 查询结果载荷 `QueryResult` 新增 `truncated: bool` 标识，当普通查询行数达到 `limit` 阈值时显式返回 `truncated: true`，赋能智能体自适应判断是否需要分页或追加过滤条件。
3. **纯环境变量多库前缀注入 (Env-based Dynamic Multi-DB)**：
   - 扩展环境变量解析器：自动扫描并解析 `MCP_RDBMS_DB_<ALIAS>=<URL>` 格式环境变量（如 `MCP_RDBMS_DB_DEV=...`、`MCP_RDBMS_DB_PROD=...`），彻底摆脱本地物理配置文件；
   - 支持通过 `MCP_RDBMS_DEFAULT_DB=<ALIAS>` 环境变量显式指定默认库，未指定时首个已注册连接自动作为默认连接。
4. **连接未找到的自愈清单与资源联动**：
   - `ConnectionNotFoundError` 增强：动态携带当前全部已注册的可用别名列表，并主动引导智能体读取静态 MCP 资源 `rdbms://connections` 快速探查连接详情。

## 效果与收益

- **闭环自愈率提升**：LLM 误调工具时无需人工干预即可在下一轮自主纠偏重定向至 `sql_dml` 或 `sql_ddl`；
- **云原生与容器集成体验极简**：支持无磁盘挂载、100% 环境变量注入的多数据库 MCP 容器部署；
- **上下文安全性增强**：微采样引导与 `truncated` 标识有效缓解宽表场景下的 Token 膨胀。
