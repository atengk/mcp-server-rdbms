# 0012: 执行计划分析 (sql_explain) AST 守卫与危险修饰符拦截

## 背景与痛点

在关系型数据库慢查询分析中，MCP 工具 `sql_explain` 旨在向大模型返回指定查询的底层执行计划（Execution Plan）。然而在主流数据库（特别是 PostgreSQL 等方言）中存在重大安全隐患：
1. **`EXPLAIN ANALYZE` 真实执行陷阱**：PostgreSQL 的 `EXPLAIN ANALYZE INSERT/UPDATE/DELETE` 会在输出计划的同时**真实执行**该修改语句。若大语言模型误生成或尝试分析写操作的执行计划，将绕过 DML 只读安全门禁并造成生产数据意外篡改；
2. **大模型 Prompt 输入异构性**：大语言模型在调用 `sql_explain` 时，有时传入纯只读 SQL（如 `SELECT ...`），有时习惯性传入自带前缀的语句（如 `EXPLAIN SELECT ...`）。

## 架构决策

我们确立了专门的 `ASTGuard.validate_explain_query` 执行计划安全校验策略：
1. **危险修饰符静态正则拦截**：
   - 严禁出现 `\b(analyze|execute)\b` 关键字，一旦检测到立即驳回并抛出 `SecurityViolationError`，杜绝一切伴随真实写操作的执行计划风险；
2. **前置 `EXPLAIN` 智能剥离**：
   - 自动识别并剥离输入语句前置的 `EXPLAIN` 词条，精准提取内层核心查询，提升对大模型不同提示词形态的自适应兼容性；
3. **内层查询全量 AST 只读守卫**：
   - 将内层语句送入 `ASTGuard.validate_read_only` 执行语法树深度校验，严格限定为只读语句（`Select`, `Union` 等），坚决拦截 `Insert`, `Update`, `Delete`, `Drop`, `Create` 等任何非只读节点。

## 收益与结果

- 杜绝了“分析执行计划却意外修改生产数据”的灾难级黑天鹅漏洞；
- 兼顾了大模型输入的容错性与数据库执行计划生成的准确性。
