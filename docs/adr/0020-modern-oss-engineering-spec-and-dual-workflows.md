# 0020: 现代化开源工程规范集成与二元自动化流水线架构

## 背景与痛点

随着 `atengk-mcp-server-rdbms` 逐步迈入稳定成熟期并面向全球开源社区分发，现存的工程基础设施暴露出若干规范化与自动化瓶颈：
1. **持续集成机制原始粗放**：原有的基础 CI 流水线缺乏改动路径探测机制，纯文档或说明性修改依然触发重型单元测试，造成 GitHub Actions 算力浪费；同时缺少动态并发控制，陈旧提交无法自动中断；
2. **发版编排单体耦合且缺乏校验**：现有发版流程缺乏“一次构建、全域分发 (Build Once, Distribute Everywhere)”的不可变校验架构，多渠道分发（PyPI、GHCR、GitHub Releases）未形成严格的 SHA-256 校验和审计与发布门禁；
3. **本地代码提交规范缺位**：代码库强依赖 Conventional Commits 规范以支撑 `git-cliff` 自动提取 Changelog，但本地开发缺乏原生提交信息守门拦截（Git Hook），容易导致不合规提交混入主干；
4. **开源社区治理文档不全**：缺乏行业标准的行为准则（`CODE_OF_CONDUCT.md`）、漏洞安全响应与披露策略（`SECURITY.md`）以及自动化依赖安全升级规范（`dependabot.yml`）。

## 架构决策

基于开源模版仓库 [`atengk/oss-template`](https://github.com/atengk/oss-template) 的标准规范架构，结合本项目 Python 3.12 与 `uv` 依赖管理的技术栈特性，我们做出以下集成决策：

1. **二元工作流分流架构 (Dual Workflows)**：
   - **PR 质量门禁流水线 (`.github/workflows/ci.yml`)**：
     - 集成 Conventional Commits PR 标题严格校验；
     - 引入 `dorny/paths-filter` **短路直通网关 (Path Fast-Pass)**，当仅修改 `*.md`、文档或静态文件时，秒级快速放行通过，彻底消除 GitHub 分支保护规则死锁；
     - 启用动态并发控制（`concurrency`）：PR 提交自动中断陈旧运行，主干提交排队保序；
     - 依赖与测试引擎深度对齐现代 `astral-sh/setup-uv`，执行 `uv sync`、`uv run ruff check` 与 `uv run pytest`，保持与 `uv.lock` 字节级一致；
     - 提供统一的终审门禁看板（`all-checks-passed`）与结构化 Step Summary 报表。
   - **统合发版编排流水线 (`.github/workflows/release.yml`)**：
     - 遵从“Build Once, Distribute Everywhere”不可变原则；
     - 严格设立发版前置质量门禁（`gate-test`），全套单测与静态检查通过后方可推进打包；
     - 单次编译构建 sdist 与 wheel，计算 `SHA256SUMS.txt` 校验和并跨 Job 流转；
     - 三路并行分发：
       1. **GitHub Releases**：自动提取 `git-cliff` 更新日志并挂载制品与校验和清单；
       2. **PyPI 官方包分发**：支持现代 OIDC Trusted Publishing 免密认证；
       3. **GHCR Docker 镜像**：基于 `Dockerfile` 自动构建 `linux/amd64` 与 `linux/arm64` 双架构镜像并推送至 `ghcr.io/atengk/mcp-server-rdbms`。
2. **轻量本地提交守护 (Commit-Msg Guard)**：
   - 引入原生 Shell 编写的 `.githooks/commit-msg` 钩子，兼容 Linux、macOS 与 Windows Git Bash 环境；
   - 激活 `git config core.hooksPath .githooks`，本地提交若不符合 Conventional Commits 格式则强行中断并输出结构化提示与样例；
   - 坚守纯原生理念，不引入侵入式 `scripts/` 目录，避免非必要脚本污染项目根目录。
3. **开源治理与安全响应体系标准化**：
   - 引入 `.github/dependabot.yml`，每周自动化排查 GitHub Actions 与 Python (`pip/uv`) 依赖包的安全漏洞并提出升级 PR；
   - 引入 `CODE_OF_CONDUCT.md`（遵循 Contributor Covenant 2.1 行为准则）；
   - 引入 `SECURITY.md`（遵循 Responsible Disclosure 漏洞披露政策并精准替换联系人邮箱）；
   - 全面升级 `CONTRIBUTING.md`，对齐最新 6 核心工具架构、测试指令与 PR 提交流程。

## 收益与结果

- CI 流水线算力消耗显著下降，纯文档 PR 实现秒级短路合入；
- 发版制品具备强不可变哈希审计，彻底根绝版本坏包分发风险；
- 本地与远端双层 Conventional Commits 守门闭环，版本发布日志自动化达到生产级工业水准；
- 仓库社区治理体系完全达到顶级开源项目准则。
