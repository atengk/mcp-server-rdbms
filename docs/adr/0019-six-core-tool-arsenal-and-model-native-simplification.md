# 0019: 极简六工具矩阵与大模型内生能力信任重构

## 背景与痛点

在项目演进至 9 核心工具矩阵（v1.1.4）的过程中，服务逐渐显现出过度适配（Over-adaptation）与职责重叠的工程瓶颈：
1. **过度适配与方言碎片化**：`admin_list_running_queries` 试图在服务端替大模型适配各类底层数据库的活动进程与慢查询视图（如 `pg_stat_activity`、`information_schema.processlist`），难以穷尽适配 Oracle（`v$session`）、SQL Server（`sys.dm_exec_requests`）或 ClickHouse（`system.processes`），且频繁受到云端细粒度运维权限缺失的困扰；
2. **忽视大模型内生 SQL 能力**：现代大语言模型具备极强的 SQL 生成与系统视图理解能力，模型完全可以依据方言自主生成查询语句并借助 `sql_query` 执行，无需服务端硬编码脆弱的胶水代码；
3. **只读探查职责重叠**：连接探查被割裂为 `db_list_connections` 与 `db_get_info` 两次独立调用；只读分析被割裂为 `sql_query` 与 `sql_explain` 两个并行工具，增加了智能体在工具选择上的幻觉与调用往返；
4. **企业级大库场景欠缺**：面对上千张表的大型模式时，表清单全量扫描缺乏按需过滤，极易导致 I/O 阻塞并冲垮上下文窗口。

## 架构决策

我们决定确立“**大模型内生能力信任原则**”，对系统实施奥卡姆剃刀式精简，从 9 核心工具重构收敛为**极简 6 核心工具矩阵**，并按需强化深层机制：

1. **确立大模型内生能力信任原则 (Model-Native Capability Principle)**：
   - 彻底废除并裁撤专职运维工具 `admin_list_running_queries`，彻底移除 `admin_` 领域命名空间；
   - 将活动进程观测、慢查询探查及原生 DDL 导出等可由只读 SQL 表达的场景完全归还给大模型，通过通用安全的 `sql_query` 自主完成，杜绝无意义的服务端专有方言适配。
2. **连接域与只读分析域高内聚收敛**：
   - **连接域二合一与优雅降级容灾**：将 `db_list_connections` 与 `db_get_info` 合并为单一 `db_info(db: str | None = None)`。在默认库发生网络不可达或宕机时，实施容灾降级，正常返回内存级静态连接清单，仅在当前连接状态标记错误，绝不中断会话；利用 SQLAlchemy 连接池超时机制（短平快探测）防止探活长时间卡死；
   - **只读分析二合一与规范统一**：将 `sql_explain` 并入 `sql_query(sql, explain=False, ...)`。当开启执行计划时，无缝继承 ADR-0012 的安全防御护栏（强校验剥离 `ANALYZE/EXECUTE` 危险修饰符并适配方言前缀），且绝对不追加自动 LIMIT 注入；借助 SQLAlchemy 统一的 `mappings()` 游标解构，将异构方言的执行计划无缝转化为标准只读行字典输出。
3. **坚守写操作物理隔离底线 (Invariant 3 & 4)**：
   - 坚决保留独立的 `sql_dml`（原子事务，防恒真条件，受 `--allow-dml` 门禁管控）与 `sql_ddl`（结构变更，受 `--allow-ddl` 管控与二次确认）；
   - 严禁将数据变更与结构定义混为单一执行工具，守牢生产权限与不可逆破坏防护红线。
4. **大库防穿透与上下文保护机制**：
   - 在 `schema_list_tables` 中将 `include_foreign_keys` 缺省值设为 `False`，消灭上百张表时的 N+1 循环网络往返，仅在用户显式需要时才聚合全库拓扑；
   - 扩展可选 `pattern`（基于 Python `fnmatch` 内存过滤），避免大库模式扫描导致上下文冲垮；
   - 在 `SafeSerializer` 中对超长纯文本字段提供自适应安全截断，防止非结构化大文本冲垮对话上下文。
5. **协议层接入模式资源暴露器与版本断舍离**：
   - 严格在 FastMCP 层面仅对外暴露 6 个标准工具，彻底废除旧工具名，杜绝大模型在工具注册表中产生选择幻觉与冗余认知负担；
   - 提供 `rdbms://connections` 与 `rdbms://{db}/schema` 两级只读 MCP Resources，支持智能体零 Tool Call 秒级装载全局数据库上下文。

## 收益与结果

- 核心工具矩阵由 9 个收敛为 6 个（`db_info`, `schema_list_tables`, `schema_describe_table`, `sql_query`, `sql_dml`, `sql_ddl`），工具歧义度降至最低；
- 充分发挥 SQLAlchemy 2.0 在元数据反射缓存、短超时探针、原子事务控制（`engine.begin()`）与统一结果集映射（`RowMapping`）上的基础设施效能；
- 代码库剔除近 300 行脆弱且不通用的各方言运维视图查询代码，降低了维护与测试成本；
- 兼顾了极简工具心智模型与严密的读写安全防御体系。
