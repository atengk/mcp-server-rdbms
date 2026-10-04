# mcp-server-rdbms 统一领域上下文 (CONTEXT.md)

通用关系型数据库模型上下文协议（MCP）服务，面向大语言模型提供标准化、可控的安全数据库交互。

## 统一语言与术语表 (Language)

**连接配置 (Connection Profile)**:
单一目标数据库的连接声明，包含连接串 URL、只读模式及连接池参数。
_避免使用_: 数据源 (Data Source)、DB 配置 (DB Config)、库实例 (DB Instance)

**连接注册表 (Connection Registry)**:
管理全部活跃数据库引擎生命周期与多库路由定位的中央管理者。
_避免使用_: 连接池管理器 (Pool Manager)、引擎工厂 (Engine Factory)

**AST 安全守卫 (AST Guardrail)**:
在 SQL 执行前拦截语法树、校验只读性、防御越权并自动追加 LIMIT 截断的安全分析层。
_避免使用_: SQL 过滤器 (SQL Filter)、安全校验器 (Sanitizer)、查询检查器 (Query Checker)

**原子变更 (Atomic Mutation)**:
由单个事务包裹、支持单条或批量执行的数据修改操作，任意单步失败则整体全量回滚。
_避免使用_: 批处理脚本 (Batch Script)、多语句执行 (Multi-statement Run)

**方言拦截器 (Dialect Interceptor)**:
检测目标连接协议是否缺失本地驱动，并智能输出一键安装命令的自适应诊断机制。
_避免使用_: 驱动加载器 (Driver Loader)、异常处理器 (Error Handler)

**领域命名空间 (Tool Namespace)**:
按 `db_`、`schema_`、`sql_`、`admin_` 对工具进行职责隔离的结构化前缀体系。
_避免使用_: 工具分类 (Tool Category)、模块前缀 (Module Prefix)

**安全序列化器 (Safe Serializer)**:
将 Decimal、时间、UUID 与二进制数据安全转换为 JSON 兼容结构并截断超大 BLOB 的类型适配器。
_避免使用_: 数据格式化器 (Data Formatter)、JSON 转换器 (JSON Dumper)

**超时熔断器 (Circuit Breaker)**:
在设定时限（默认 30s）内强行中断长时间失控慢查询并释放连接的守护机制。
_避免使用_: 超时控制器 (Timeout Controller)、看门狗 (Watchdog)

**模式过滤器 (Schema Filter)**:
自动排除数据库底层系统保留 Schema 与系统视图、仅暴露用户业务表的过滤层。
_避免使用_: 系统表黑名单 (Blacklist)、表名白名单 (Whitelist)

**连接摘要 (Connection Summary)**:
包含连接别名、方言、脱敏 URL、只读状态与默认标识的轻量级连接描述载荷。
_避免使用_: 数据库信息 (DB Info)、连接详情 (Connection Detail)

**发布产物 (Distribution Artifact)**:
经由现代构建工具打包生成的标准 wheel 二进制轮子包与源码分发压缩包。
_避免使用_: 安装包 (Setup Package)、构建物 (Build Output)

**发布流水线 (Release Pipeline)**:
监听 Git 版本标签自动执行质量门禁、多环境校验并推送到公网包索引的持续交付工作流。
_避免使用_: 发版脚本 (Release Script)、发布动作 (Publish Action)

**发布说明 (Release Notes)**:
结构化呈现实体版本核心特性、快速上手命令与兼容性变更的正式发版宣言。
_避免使用_: 更新日志草稿 (Changelog Draft)、发版文案 (Release Text)

**品牌命名空间 (Brand Scoped Namespace)**:
以 `atengk-mcp-server-` 为规范前缀的系列化 MCP 服务产品矩阵体系，用于在全局扁平包索引中建立唯一的专属命名空间隔离与品牌辨识。
_避免使用_: 用户名前缀 (User Prefix)、账号作用域 (Account Scope)

