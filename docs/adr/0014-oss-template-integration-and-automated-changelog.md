# 0014: 集成开源模版工程规范、自动化 CI 与 git-cliff 更新日志流

## 背景与痛点

随着 `atengk-mcp-server-rdbms` 逐步迈向成熟的开源产品，面对外部社区协作与持续分发，存在以下工程化痛点：
1. **多环境换行符与格式不一致**：在 Windows 与 Linux/macOS 交叉开发时，缺少 `.gitattributes` 与 `.editorconfig` 约束，容易出现换行符报警与缩进不一；
2. **缺乏日常 PR 持续集成门禁**：此前仅在 Tag 发版时运行一次流水线，缺乏在日常向 `main` 分支提交或外部 Pull Request 时的自动化代码规范检查与单元测试验证；
3. **手写 CHANGELOG.md 维护摩擦**：随着发布节奏加快，人工手写 `CHANGELOG.md` 不仅耗费心智，还容易遗漏某些局部提交；
4. **容器镜像分发途径受限**：虽然提供了 Dockerfile，但用户仍需自行本地 build，缺少官方自动构建发布的公共容器镜像源。

## 架构决策

全面集成 [`atengk/oss-template`](https://github.com/atengk/oss-template) 开源模板基础设施并深度本地化适配：

1. **工程基础设施统一**：
   - 引入 `.editorconfig` 统一跨编辑器 UTF-8、LF 及 Python 4 空格缩进；
   - 引入 `.gitattributes` 强制文本文件换行符归一化为 LF，针对 Windows 脚本保留 CRLF；
   - 建立高规格社区规范：定制化 `CONTRIBUTING.md`、`.github/PULL_REQUEST_TEMPLATE.md` 与 Issue 模版（Bug 报告与特性建议）。
2. **日常 CI 自动化门禁流水线 (`.github/workflows/ci.yml`)**：
   - 集成 `amannn/action-semantic-pull-request` 严格校验 PR 标题符合 Conventional Commits 规范；
   - 集成 `astral-sh/setup-uv`，在 push 和 PR 时自动执行 `ruff check` 静态语法分析与 `pytest -s` 全量单元测试。
3. **完全自动化更新日志流水线 (`.cliff.toml`)**：
   - 彻底废除人工手写 `CHANGELOG.md` 模式，引入 `git-cliff` 自动化工具；
   - 在 `.github/workflows/release.yml` 中集成 `orhun/git-cliff-action@v4`，发版时自动基于 Conventional Commits 历史提取生成结构化 Release 说明。
4. **全自动多架构 GHCR 镜像分发 (`publish-docker`)**：
   - 在发版流水线中扩展 `publish-docker` Job，基于系统内置 `GITHUB_TOKEN` 自动登录 GitHub Container Registry；
   - 自动构建并推送 `linux/amd64` 与 `linux/arm64` 双架构镜像至 `ghcr.io/atengk/mcp-server-rdbms:latest` 与版本 Tag。

## 收益与结果

- 建立了工业级的开源规范与社区协作治理机制；
- 实现了“Commit 即发布日志”、“打 Tag 即全渠道分发（PyPI + GHCR + GitHub Release）”的完全免人工运维飞跃。
