# 0031: 双模动态数据脱敏、审计字面量净化与脱敏列回显架构

- **状态**: Accepted
- **日期**: 2026-11-07
- **决定者**: Ateng

## 背景与痛点

在大语言模型通过 `mcp-server-rdbms` 执行业务数据探查（如 `SELECT *` 采样）与数据变更（`sql_dml`）时，尽管此前已在连接摘要层实现了连接串密码脱敏（ADR-0008），但业务数据与审计日志层面仍面临以下隐私与机密泄露风险：

1. **查询结果集明文暴露 (PII & Credential Exposure)**：业务表中的个人敏感信息（手机号、身份证号、电子邮箱、银行卡号）及高危凭据列（`password`、`secret`、`token`、`api_key` 等）在 `sql_query` 采样时直接以明文流入大模型上下文窗口；
2. **单一识别机制存在盲区与误报冲突**：
   - 纯列名匹配容易被 `SELECT phone AS col1` 列别名重命名或嵌套 JSON 文本绕过；
   - 纯值内容正则匹配无法识别无固定格式的密码哈希、盐值或自定义密钥，且宽泛的列名匹配容易将 `token_count`、`email_verified`、MySQL `EXPLAIN` 中的 `key` 索引列等非敏感衍生字段误伤为掩码；
3. **审计日志字面量残留**：当开启 `MCP_RDBMS_AUDIT_MODE=mutation` 或 `all` 时，SQL 语句及异常报错堆栈中内嵌的密码赋值或手机号字面量会被原样写入 `rdbms_mcp_audit.log` 并通过 `rdbms://audit/recent` 资源暴露；
4. **大模型“掩码当真值”回写污染风险**：若服务端静默将结果集中的 `13800138000` 替换为 `138****8000` 而不做契约级显式声明，大模型可能误判数据库底层存储的即为带星号文本，进而在后续 `WHERE` 过滤或 `UPDATE` 语句中使用掩码值造成查询失效或生产数据污染。

## 架构决策

经 Grilling 设计树推演，决定在**结果集序列化层**与**独立审计流水层**构建默认开启（Secure-by-Default）的**动态数据脱敏器（Dynamic Data Masker）**体系，而不在 `ASTGuard` 层封禁基础字符串函数（保持无状态静态语法树校验与大模型正常 SQL 分析能力，底层列级强隔离交由数据库原生权限实现纵深防御）：

1. **列名匹配 + 值内容特征双模驱动引擎 (Hybrid Dual-Engine)**：
   - **高危凭据列（全掩码 `******`）**：精准匹配 `password`、`passwd`、`pwd`、`secret`、`token`、`api_key`、`apikey`、`secret_key`、`private_key`、`access_key`、`auth_key`、`client_secret`、`credential`、`salt`（禁用宽泛单字 `key`，防止误杀 `sort_key` 或索引名）；
   - **个人隐私列与值特征正则（局部保留掩码）**：内置识别中国大陆 11 位手机号（前 3 后 4，如 `138****5678`）、15/18 位身份证号（前 6 后 4）、电子邮箱（`u***@domain.com`）、16~19 位银行卡号（前 4 后 4）及常见高危密钥前缀（`sk-`、`ghp_`、`AKIA`、`Bearer `、PEM 私钥头）；
   - **嵌套结构穿透**：递归穿透原生 `dict`/`list` 及单元格内的 JSON 格式字符串，对内部键名与值同步执行双模脱敏；
   - **防误伤双重豁免机制**：
     1. 内置规则下，布尔值、日期时间、浮点数及长度小于 11 位的短整数免于脱敏；
     2. 列名命中状态/计数词缀（`is_*`, `has_*`, `*_count`, `*_num`, `*_status`, `*_state`, `*_type`, `*_flag`, `*_time`, `*_at`, `*_date`）时豁免凭据列全掩码；
     3. `sql_query(explain=True)` 执行计划模式下跳过基于列名的脱敏，防止误伤优化器元数据列（如 MySQL `EXPLAIN` 的 `key` 列）。

2. **多级配置与用户自定义敏感列 (Hierarchical Mask Configuration)**：
   - **全局配置**：引入环境变量 `MCP_RDBMS_MASK_ENABLED`（默认 `true`）/ CLI `--no-mask`，以及自定义追加敏感列配置 `MCP_RDBMS_MASK_COLUMNS` / CLI `--mask-columns`（支持逗号分隔词素与通配符）；
   - **连接级细粒度覆盖**：在 `connections.yaml` 的 `ConnectionProfile` 中支持可选的 `mask_enabled: bool | None = None` 与 `mask_columns`，显式声明时优先于全局配置；在 `ConnectionSummary` 与 `--doctor` 诊断报告中同步暴露脱敏状态；
   - **自定义列强制掩码与自适应样式**：命中用户显式声明的 `mask_columns` 时，不豁免数值类型（数值统一掩码为 `******`）；未命中特种正则的普通字符串采用自适应首尾保留掩码（1 字为 `*`，2 字保留首字如 `张*`，3~6 字保留首尾如 `王*二`，7 字及以上保留前 2 后 2、中间 `****`）。

3. **审计字面量脱敏 (Audit Literal Sanitization)**：
   - 在 `AuditLogger` 落盘及 `rdbms://audit/recent` 暴露前，通过预编译轻量正则自动掩码 SQL `statements` 与 `error` 报错信息中的隐私值特征及敏感列赋值字面量（如 `password = '...'`、`"secret": "..."`），零 AST 解析开销且对语法错误的失败 SQL 同样生效。

4. **脱敏列回显防幻觉契约 (Masked Column Echo)**：
   - 在 `QueryResult` 契约中新增 `masked_columns: list[str] = field(default_factory=list)`（未触发脱敏时返回空列表 `[]`）；
   - 凡单元格（含内部嵌套 JSON）发生动态掩码，均将该顶层列名记录至 `masked_columns`，明确告知大模型对应列已被安全护栏掩码，严禁将掩码占位符用于后续 `WHERE` 条件或 `DML` 写入。

## 效果与收益

- **开箱即用隐私合规**：默认拦截明文密码、密钥与个人隐私流入大模型上下文及本地审计日志；
- **高精度零误伤**：兼顾无固定格式密码列的 100% 召回、列别名重命名防穿透，以及状态/计数列与 `EXPLAIN` 索引列的零误报；
- **消除回写污染**：通过 `masked_columns` 结构化契约回显，阻断大模型将掩码值误判为真实库表数据的幻觉链路；
- **平滑向后兼容**：不破坏既有 6 核心工具签名与静态 AST 校验性能。
