# 0011: 分层环境变量解析与连接串自动拼装架构

## 背景与痛点

在容器化部署 (Docker/K8s) 以及各类 AI 客户端 (Claude Desktop, Cursor, VS Code) 配置 MCP 服务时，直接暴露包含账号密码的命令行参数 (`--db-url`) 存在安全隐患与进程泄露风险。同时，传统配置数据库连接串有两大严重阻碍：
1. **密码特殊字符转义门槛**：用户密码中常包含 `@`, `#`, `:`, `/`, `?` 等字符。SQLAlchemy RFC 1738 连接串要求手工转义为 `%40`、`%23`，用户极易遗漏或因转义错误导致服务启动失败；
2. **缺乏统一前缀与云原生标准**：不同环境和开发者习惯不同，有的使用标准 `DATABASE_URL`，有的使用云平台容器的独立字段（如 `DB_HOST`, `DB_USER`, `DB_PASSWORD`）。

## 架构决策

我们确立了 **分层环境变量解析 (Hierarchical Env Resolution)** 与 **环境自动拼装器 (Env Auto Assembler)**：

1. **统一前缀与兼容矩阵**：
   - 官方主推荐前缀为 `MCP_RDBMS_*`（如 `MCP_RDBMS_DB_URL`, `MCP_RDBMS_CONFIG`, `MCP_RDBMS_ALLOW_DML`）；
   - 同时宽容回退兼容通用的无前缀行业标准变量（如 `DATABASE_URL`, `DB_HOST`, `DB_PORT`, `PORT` 等）。
2. **独立原子字段安全拼装与防二次编码**：
   - 当未提供完整 URL 时，自动扫描 `DIALECT`、`USER`、`PASSWORD`、`HOST`、`PORT`、`DATABASE`；
   - 内部对密码执行 `urllib.parse.unquote_plus` 还原后再执行 `urllib.parse.quote_plus` 转义。用户无论输入纯明文还是已编码密码，均能 100% 正确生成合规连接串，彻底根除用户特殊字符踩坑痛点。
3. **宽容布尔转换 (Tolerant Boolean)**：
   - 权限门禁变量对 `1`, `true`, `yes`, `on`, `t` 大小写及首尾空格进行归一化宽容解析。
4. **解析优先级契约**：
   - `CLI 参数 (最高)` > `全量 URL 环境变量` > `独立字段环境变量拼装` > `标准内置默认值`。

## 收益与结果

- 达成 100% 容器无参启动（12-Factor App）；
- 彻底解决用户因密码特殊字符未转义导致连接失败的高频排错成本；
- 模块解耦：抽离为独立纯计算无副作用单元 `core/env.py`，保持装配入口 `cli.py` 轻薄。
