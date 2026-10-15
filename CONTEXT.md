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
按 `db_`、`schema_`、`sql_` 对工具进行职责隔离的结构化前缀体系。
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

**分层环境变量解析器 (Hierarchical Env Resolver)**:
统一支持 CLI 参数、全量连接串、独立原子字段、运行权限与传输协议的分层回退解析体系。
_避免使用_: 环境加载器 (Env Loader)、参数合并器 (Args Merger)

**环境自动拼装器 (Env Auto Assembler)**:
将独立环境变量（方言、主机、端口、用户、密码、库名）自动合成符合 RFC 1738 规范的数据库连接串，并对特殊字符密码自动执行 URL 编码的安全拼装器。
_避免使用_: URL 拼接函数 (URL Builder)、连接串合成器 (String Concat)

**宽容布尔转换器 (Tolerant Boolean Converter)**:
将多源字符串（`1, true, yes, on, t`，不区分大小写及首尾空格）统一可靠映射为标准 Python 布尔状态的解析适配器。
_避免使用_: 布尔检查器 (Bool Checker)、Flag 转换器 (Flag Parser)

**执行计划守卫 (Explain Guardrail)**:
在生成慢查询执行计划前拦截危险 ANALYZE 选项、剥离冗余修饰并校验内层语法树只读性的防御层。
_避免使用_: 执行计划检查器 (Plan Checker)、EXPLAIN 解析器 (Explain Parser)

**本地环境探测器 (Dotenv Detector)**:
在零外部依赖前提下自适应嗅探本地 `.env` 并在系统环境变量未设定时轻量注入的加载机制。
_避免使用_: Dotenv 注入器 (Dotenv Injector)、文件加载器 (File Loader)

**语义化拉取请求校验器 (Semantic PR Validator)**:
在持续集成中自动依据 Conventional Commits 规范检验 Pull Request 标题合法性的自动化审查门禁。
_避免使用_: PR 标题检查器 (PR Title Checker)、提交门禁 (Commit Gate)

**自动化变更日志生成器 (Automated Changelog Generator)**:
由 git-cliff 基于语义化提交历史自动提取、归类与渲染版本发布日志的免运维流水线。
_避免使用_: 日志生成脚本 (Changelog Script)、发版备忘录 (Release Notes Generator)

**容器镜像注册表分发器 (Container Registry Publisher)**:
在版本发布时自动构建多架构 Docker 镜像并推送至 GHCR (GitHub Container Registry) 的持续交付作业。
_避免使用_: 镜像打包脚本 (Image Packager)、Docker 推送器 (Docker Pusher)

**零物理变更日志 (Stateless Zero-File Changelog)**:
项目中绝对不保留或维护静态 `CHANGELOG.md` 物理文件，版本历史 100% 依托 Conventional Commits 规范并通过 `.cliff.toml` 动态提取渲染至 GitHub Releases 的极简无状态架构。
_避免使用_: 手写更新日志 (Manual Changelog)、静态日志文件 (Changelog File)

**官方预构建容器编排器 (Pre-built Container Orchestrator)**:
以 GHCR 云端多架构预构建镜像（`ghcr.io/atengk/mcp-server-rdbms`）为核心运行载荷的 Docker Compose 编排模式，实现最终用户零编译、免安装依赖、秒级拉起常驻守护容器，仅在开发者调试时可选解开源码构建指令。
_避免使用_: 源码构建编排 (Source Build Compose)、混合编排器 (Hybrid Orchestrator)

**纯净镜像分发矩阵 (Clean Multi-arch Image Matrix)**:
严格遵循 SemVer 规范计算镜像标签（主版本、次版本、补丁版本与自适应 `latest`），并显式声明 `provenance: false` 与 `sbom: false` 以彻底杜绝 Registry 幽灵标签与多架构索引冲突的纯净容器分发模式。
_避免使用_: 冗余标签策略 (Redundant Tagging)、单架构打包 (Single Arch Build)

**动态元数据版本反射 (Dynamic Metadata Versioning)**:
遵循单一真实数据源 (SSOT) 原则，仅在 `pyproject.toml` 维护版本号，模块顶层通过标准库 `importlib.metadata.version` 动态读取运行时包版本的解耦设计。
_避免使用_: 硬编码版本 (Hardcoded Version)、双重版本维护 (Dual Version Maintenance)

**恒真条件护栏 (Trivial WHERE Guard)**:
静态识别并拦截 `1=1`、`true` 等恒真布尔表达式以杜绝伪装条件全表意外篡改或删除的语法树分析机制。
_避免使用_: 恒等条件过滤器 (Identity Filter)、无意义 WHERE 拦截器 (Meaningless Where Interceptor)

**锁读语句 (Locking Read)**:
显式携带 `FOR UPDATE` 或 `FOR SHARE` 等行级/表级排他或共享锁修饰以锁定目标记录的查询操作。
_避免使用_: 加锁查询 (Locked Query)、悲观锁 SQL (Pessimistic SQL)

**复合写操作 (Composite Mutation)**:
单条语句内聚合匹配、插入与更新多重语义的高级 DML 语法（如 `MERGE INTO`、`REPLACE INTO`）。
_避免使用_: 混合变更 (Mixed Mutation)、多动作 SQL (Multi-action SQL)

**纵深防御架构 (Defense-in-Depth Architecture)**:
在 MCP 服务端 AST 静态结构校验与数据库端账号最小只读特权之间形成互补的双层安全边界体系。
_避免使用_: 混合防御 (Hybrid Defense)、内外安全机制 (Internal-External Security)

**模式资源暴露器 (Schema Resource Provider)**:
将连接注册表中的连接列表与表清单映射为 MCP 标准只读 URI 资源的协议适配层。
_避免使用_: 资源加载器 (Resource Loader)、Schema 资源接口 (Schema Resource API)

**极简六工具矩阵 (Six-Core Tool Arsenal)**:
基于纯粹语义与读写隔离构建的高内聚 MCP 工具集合（`db_info`、`schema_list_tables`、`schema_describe_table`、`sql_query`、`sql_dml`、`sql_ddl`）。
_避免使用_: 基础工具集 (Basic Tools)、核心八工具 (Eight Tools)

**大模型内生能力信任原则 (Model-Native Capability Principle)**:
避免在服务端硬编码脆弱的方言专有适配，将可通过通用标准只读 SQL 自主探查的运维与方言元数据职责完全归还给大模型的极简设计哲学。
_避免使用_: 客户端自主性 (Client Autonomy)、免适配设计 (No-adapter Design)

**模式过滤模式 (Schema Filter Pattern)**:
在表清单探查中支持通配符或前缀匹配过滤，避免大库全量扫描导致 I/O 阻塞与上下文爆炸的按需探查策略。
_避免使用_: 表名正则匹配 (Table Regex)、模糊搜索 (Fuzzy Search)

**自适应文本截断 (Adaptive Text Truncation)**:
在安全序列化层对超长纯文本字段提供字符长度探测与安全截断标注，防止单字段冲垮客户端对话上下文的防护机制。
_避免使用_: 字符串截断器 (String Truncater)、大字段剪裁 (Bigfield Clipper)

**二元工作流 (Dual Workflows)**:
将开源工程自动化流水分离为聚焦 PR 规范与质量门禁的 CI 流程，以及聚焦不可变制品与多渠道分发的统合 Release 编排流程。
_避免使用_: 混合流水线 (Mixed Pipeline)、单体 CI/CD (Monolithic CI/CD)

**短路直通网关 (Path Fast-Pass Gateway)**:
基于改动文件路径动态分析，在纯文档或静态资源变更时秒级放行流水线，消除分支保护规则死锁的机制。
_避免使用_: 文档跳过器 (Docs Skipper)、假绿灯 (Fake Green)

**不可变发行制品 (Immutable Release Artifacts)**:
在统合发版流水线中单次编译构建并计算 SHA-256 校验和，供 GitHub Release、PyPI 及 Docker 多路复用分发的归档产物。
_避免使用_: 动态构建物 (Dynamic Builds)、随地打包 (Ad-hoc Packaging)

**提交守护守门 (Commit-Msg Guard)**:
通过本地 Git Hook 在每次代码提交时拦截不符合 Conventional Commits 规范的提交信息以保障版本日志自动化的守门机制。
_避免使用_: 提交拦截器 (Commit Blocker)、信息验证器 (Message Validator)

**专利防卫许可 (Patent Retaliation License)**:
基于 Apache License 2.0 构建的开源法律授权体系，提供显式专利授权与专利反诉自动终止条款，保障原作者与采用者法律安全。
_避免使用_: 基础开源协议 (Basic License)、通用授权 (General License)

**自愈型拦截重定向 (Self-Healing Remediation)**:
在安全守卫拦截非法操作（如只读通道误入写语句）时，主动在错误载荷中输出下一跳适配工具与权限指引以赋能大模型自主纠偏的机制。
_避免使用_: 错误回显 (Error Echo)、错误增强 (Error Augmentation)

**零配置多库注入 (Zero-Config Multi-DB)**:
无需在本地创建物理配置文件，直接通过 `MCP_RDBMS_DB_<ALIAS>` 与 `MCP_RDBMS_DEFAULT_DB` 环境变量完成多数据库实例声明与默认库绑定的轻量注入机制。
_避免使用_: 环境变量魔改 (Env Hacking)、动态数据源注入 (Dynamic Source Injection)

**微采样引导 (Micro-Sampling Guidance)**:
在工具契约中主动向大模型传达针对未知宽表使用极小 LIMIT（3~5 行）探查数据结构的节制使用心智，防范上下文溢出。
_避免使用_: 数据偷窥 (Data Peeking)、小批量抽取 (Small Batch Fetch)

**专属环境命名空间 (Dedicated Env Namespace)**:
严格以 `MCP_RDBMS_*` 为唯一合法前缀的环境变量体系，彻底排除 `DATABASE_URL`、`PORT`、`HOST` 等通用无前缀变量以物理级防御跨进程配置污染与意外串库。
_避免使用_: 通用环境变量 (Generic Env)、兼容别名变量 (Alias Env)

**基线运行时锁定 (Baseline Runtime Pinning)**:
将生产容器镜像与核心构建环境严格固化在受充分验证的长期支持版本（如 Python 3.12-slim），拦截未经广泛驱动兼容测试的早期预览版镜像冒进合入的依赖管控规范。
_避免使用_: 版本冻结 (Version Freeze)、镜像锁死 (Image Lock)

**协同动作依赖对齐 (Coordinated Action Upgrades)**:
在 CI/CD 流水线中针对具备强协议握手或状态解包依赖的成对工作流动作（如 upload-artifact 与 download-artifact）实施协同一致性升级，严禁单侧跨大版本孤立升级引发流水线断裂的工程纪律。
_避免使用_: 单边升级 (Unilateral Upgrade)、动作混用 (Action Mixing)

**分级审计模式 (Graded Audit Mode)**:
支持 `mutation`（仅写操作）、`all`（包含只读查询）与 `off`（关闭审计）三档动态分级的操作审计运行机制，兼顾合规深度与运行性能。
_避免使用_: 审计开关 (Audit Switch)、日志级别 (Log Level)

**审计资源暴露器 (Audit Resource Provider)**:
将本地审计日志文件抽象并挂载为 MCP 标准只读资源端点（`rdbms://audit/recent`），供 AI 智能体零 Tool Call 自主查阅近期执行流水与历史记录的协议适配层。
_避免使用_: 审计查看工具 (Audit Tool)、日志接口 (Log API)

**审计防爆截断器 (Audit Truncation Guard)**:
在审计落盘前对超长 SQL 语句（超过 4096 字符）与超量批量操作（超过 100 条）实施智能字符折叠与数量截断、物理级防御磁盘被异常大文本日志击穿的安全守护机制。
_避免使用_: 字符剪裁器 (String Cutter)、批量限制器 (Batch Limiter)

**环境体检探针 (Doctor Diagnostics)**:
在服务运行前对 Python 基础环境、SQLAlchemy 运行时、驱动就绪矩阵、专属环境变量命名空间与已配置数据库连通性进行分层全面自检并生成结构化诊断报告的客户端运维探针。
_避免使用_: 环境自检 (Self-check)、健康检查接口 (Health Check API)、Debug 模式 (Debug Mode)

**驱动矩阵探测器 (Driver Matrix Probe)**:
静态探测 9 大主流关系型数据库方言驱动的安装就绪状态，对未就绪驱动输出精准一键安装指引并评估当前环境驱动支持度的组件。
_避免使用_: 驱动检查器 (Driver Checker)、依赖嗅探器 (Dependency Sniffer)

**无串库环境审计 (Namespace Hygiene Audit)**:
在自检中扫描宿主环境，主动发现被废弃或易混淆的通用无前缀变量（如 DATABASE_URL）并告警其已被安全忽略，同时校验专属命名空间合法性的防护审计机制。
_避免使用_: 变量审计 (Var Audit)、环境清洗 (Env Sanitizer)

**服务元数据自解释 (Server Metadata Self-Explanation)**:
允许通过 CLI 参数与专属环境变量自定义 MCP 服务实例显示名称与面向大模型的业务指令说明，使智能体在多服务并发挂载时能够秒级辨识不同实例业务定位的元数据注入机制。
_避免使用_: 服务别名 (Server Alias)、自定义描述 (Custom Description)

**多库路由提示词引导 (Multi-DB Routing Guidance)**:
在全部核心数据操作工具的契约描述中显式注入多数据库识别、可用连接查询与跨库定向路由说明，消除大模型跨库执行幻觉并强化精准参数调度的提示词工程机制。
_避免使用_: 多库提示 (Multi-db Hint)、参数提示词 (Param Prompt)

**传输层令牌门禁 (Bearer Token Gate)**:
在远端网络协议（SSE / Streamable-HTTP）通信中，通过常数时间安全比对请求头或查询参数中的访问令牌，阻断未授权网络调用与自动化扫描的内置安全中间件机制。
_避免使用_: API 密码 (API Password)、简易 Token 校验 (Simple Token Check)

**反向代理网关防御 (Reverse Proxy Gateway Defense)**:
将 MCP 网络服务部署于前置网关（如 Nginx、Caddy、Envoy）之后，由网关统一收敛 TLS/HTTPS 证书加密、IP 白名单、速率限制与外部认证的纵深防御边界体系。
_避免使用_: 外部网关 (External Gateway)、代理防护 (Proxy Protection)

**安全回环绑定 (Localhost Loopback Binding)**:
在容器化或本地网络部署中，强制将服务端口仅绑定至本地回环地址（127.0.0.1）而非全网卡（0.0.0.0），物理级防御非预期的局域网或公网直接暴露的最小暴露面策略。
_避免使用_: 本地绑定 (Local Bind)、单机监听 (Single Host Listen)

**主机与来源安全白名单 (Allowed Hosts & Origins)**:
在远端网络协议模式下，显式指定或通配允许访问的 Host 域名与 Origin 来源，以精准适配反向代理与容器互联并防止被 DNS Rebinding 机制误杀的安全白名单机制。
_避免使用_: 域名白名单 (Domain Whitelist)、Host 过滤 (Host Filter)

**预检免认证穿透 (CORS Preflight Bypass)**:
在传输层令牌门禁中对浏览器发起的跨域 OPTIONS 预检请求执行免认证放行，确保 Web 版 AI 客户端在跨域接入时能够顺利完成 CORS 握手而不被误判为未授权的协议兼容机制。
_避免使用_: OPTIONS 放行 (OPTIONS Pass)、预检豁免 (Preflight Exemption)

**健康探针免认证路由 (Public Health Probe)**:
在 FastMCP 实例上注册并在令牌门禁中公开免密放行的轻量探活端点（/health 与 /ping），供 Docker Compose、Kubernetes 与负载均衡器精准探查服务存活而免受令牌拦截导致重启风暴的云原生就绪机制。
_避免使用_: 健康检查接口 (Health Endpoint)、探针白名单 (Probe Whitelist)

**优雅连接池回收 (Graceful Pool Disposal)**:
无论服务通过用户主动中断（SIGINT）、容器编排终止（SIGTERM）还是未捕获异常退出，均在顶层结构化保证（try...finally）中全量关闭并释放连接池句柄以彻底杜绝数据库悬挂连接的生命周期安全保障机制。
_避免使用_: 退出释放 (Exit Cleanup)、自动断连 (Auto Disconnect)

