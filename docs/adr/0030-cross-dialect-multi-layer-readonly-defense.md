# 0030: 跨方言多层只读纵深防御与高危副作用函数矩阵架构

- **状态**: Accepted
- **日期**: 2026-11-04
- **决定者**: Ateng

## 背景与痛点

独立安全研究员披露了 `mcp-server-rdbms` (v1.5.0) 中 `sql_query` 工具的只读防护绕过漏洞：
1. **任意文件读取与文件系统遍历 (CWE-200)**：在超级用户或具备特定读取权限角色下，攻击者通过在 `SELECT` 查询中调用未被原有黑名单覆盖的方言系统函数（如 PostgreSQL `pg_read_file`、`pg_read_binary_file`、`pg_ls_dir`、MySQL `LOAD_FILE`、SQLite `load_extension`、ClickHouse 表函数 `file()` 等），可读取任意宿主文件或遍历目录；
2. **写操作隐蔽渗透与状态持久化 (CWE-863)**：攻击者通过 `SELECT lo_import(...)`、`lo_create(...)` 等大对象函数操纵 `pg_largeobject` 元数据写入，此类持久化写操作绕过了常规 DML AST 节点拦截；
3. **黑名单防护盲区与缺少包名解析**：旧有的 `_DANGEROUS_FUNCTIONS` 仅覆盖 10 项函数，且在解析 Oracle/MSSQL/达梦的 Schema/Package 前缀函数（如 `utl_file.get_line`、`xp_cmdshell`）时无法有效匹配复合调用；
4. **底层引擎缺少只读硬隔离**：`sql_query` 仅依赖应用层 AST 静态拦截，在执行底层 SQLAlchemy 数据库连接与事务时未声明原生只读约束。

## 架构决策

经架构推演与权衡论证，我们决定弃用单一粗粒度黑名单，全面引入**静态 AST 矩阵拦截 + 跨方言会话只读适配器的立体纵深防御架构 (Defense-in-Depth)**：

1. **副作用函数防御矩阵 (Side-Effecting Function Matrix)**：
   - 全面覆盖 9 大主流及通用关系型数据库方言的高危函数特征（文件 I/O、隐式大对象持久写、远程跨库执行、进程派生、动态扩展加载与系统归档运维）；
   - 增强 AST 语法树遍历：同时支持裸函数名匹配与 `exp.Dot` 包名前缀复合匹配（如精准拦截 `utl_file.get_line`、`dbms_lob.loadfromfile` 等）；
   - 将 ClickHouse 等列式引擎的特殊数据源表函数（如 `FROM file(...)`、`FROM url(...)`、`FROM s3(...)`）同步纳入拦截范畴；
   - 保持全局统一超集集合匹配，零方言切换心智负担，内存 $O(1)$ 高性能判定。

2. **跨方言只读会话适配器 (Dialect Read-Only Session Adapter)**：
   - 在 `sql_query` 执行查询时，对底层数据库连接强制应用只读会话属性；
   - 针对已知主流方言实施策略模式初始化：
     - PostgreSQL / Kingbase: 执行 `SET default_transaction_read_only = on`；
     - MySQL / MariaDB / TiDB: 执行 `SET SESSION TRANSACTION READ ONLY`；
     - SQLite: 执行 `PRAGMA query_only = ON`；
     - Oracle / 达梦 (DM): 事务首条语句执行 `SET TRANSACTION READ ONLY`；
     - ClickHouse: 附加会话设置 `SET readonly = 1`；
   - 对未知方言实施优雅容错降级（Best-Effort with Graceful Degradation）：尝试标准只读声明，若方言不支持则记录日志降级，确保通用性不受损。

3. **双轨防御模式 (Dual-Mode Defense)**：
   - 默认启用全量副作用函数防御矩阵与跨方言会话只读适配器；
   - 提供可选严格白名单模式配置，满足特种超高安全场景需求。

## 效果与收益

- **封堵 CWE-200 与 CWE-863 漏洞**：彻底杜绝通过 `SELECT` 查询读取宿主文件与隐式写入大对象数据的漏洞通道；
- **全品类 RDBMS 纵深防护**：覆盖 PostgreSQL、MySQL、Oracle、MSSQL、ClickHouse、达梦、人大金仓与 SQLite 等全量方言；
- **双重保险**：AST 静态拦截（防御读文件与高危表函数）与数据库引擎物理只读事务（防御未预期的隐式写入）互为兜底，牢不可破；
- **无破坏性兼容**：普通只读查询、聚合分析、PostGIS 空间函数及用户合法只读函数不受任何误杀影响。
