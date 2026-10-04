# 贡献指南 (Contributing Guide)

感谢你关注并愿意为 `atengk-mcp-server-rdbms` 贡献力量！为了保持高效协作与高质量的代码维护，请在提交代码前仔细阅读以下规范。

---

## 1. 协作与分支模型

本项目遵循标准的 **GitHub Flow** 工作流：

1. **Fork 本仓库** 到你个人的 GitHub 账号；
2. **基于 `main` 分支拉取新的特性或修复分支**：
   ```bash
   git checkout -b feat/your-feature-name
   # 或者缺陷修复分支
   git checkout -b fix/issue-description
   ```
3. 在本地完成修改，确保自测通过并补充相应单元测试；
4. 运行本地工程质量检查门禁：
   ```bash
   # 1. 运行代码风格与静态类型检查
   uv run ruff check

   # 2. 运行全量单元测试
   uv run pytest -s
   ```
5. 提交更改并推送到你的远程分支：
   ```bash
   git push origin feat/your-feature-name
   ```
6. 在 GitHub 上向本仓库的 `main` 分支发起 **Pull Request**。

---

## 2. Commit 提交信息规范

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范，统一采用以下格式：

```text
<type>(<scope>): <中文描述>
```

### 常用类型说明

| 类型 | 说明 | 示例 |
| :--- | :--- | :--- |
| `feat` | 新增功能或特性 | `feat(env): 支持独立环境变量拼装与特殊字符免转义` |
| `fix` | 缺陷与 Bug 修复 | `fix(guard): 修复包含 CTE WITH 复杂语法的只读解析` |
| `docs` | 仅文档更新或修改 | `docs: 完善快速开始与容器化常驻部署指南` |
| `style` | 代码格式调整（不影响业务逻辑） | `style: 优化代码排版与注释间距` |
| `refactor` | 代码重构（既非新增特性也非修复缺陷） | `refactor(core): 抽取 ServerRuntimeConfig 契约模型` |
| `perf` | 性能优化 | `perf(pool): 优化连接池探针预检与回收周期` |
| `test` | 增加或重构单元测试 | `test: 增加 EXPLAIN ANALYZE 危险修饰符拦截单测` |
| `build` | 构建系统、外部依赖或脚手架调整 | `build: 升级 FastMCP 依赖版本` |
| `ci` | CI/CD 流水线与 GitHub Actions 脚本修改 | `ci: 增加 PR 标题规范校验与 GHCR 镜像构建` |
| `chore` | 其他琐碎杂项（不改动业务源码与测试） | `chore: 更新 .gitignore 忽略规则` |
| `revert` | 恢复或回滚此前的某次历史提交 | `revert: feat(guard): 回退语法树解析变动` |

---

## 3. 核心架构与代码约束 (Core Invariants)

在参与本项目开发时，请严格遵守以下核心底线（详见 [`AGENTS.md`](./AGENTS.md) 与 [`CONTEXT.md`](./CONTEXT.md)）：

1. **异步防阻塞**：FastMCP 运行在异步事件循环中，所有数据库 I/O 必须通过 `anyio.to_thread.run_sync` 卸载至工作线程池执行；
2. **AST 零绕过只读防御**：只读查询下发前必须由 `sqlglot` 完整解析为 AST 树，未带 LIMIT 时强制自动注入安全截断限制；
3. **默认强只读保护**：默认禁止执行任何 DML 或 DDL，仅在显式配置开启门禁时放行；
4. **DML 原子事务**：必须在单一事务块中执行，单步报错全量自动 `ROLLBACK`，强制拦截无 `WHERE` 条件的 `UPDATE`/`DELETE`；
5. **执行计划安全守卫**：`sql_explain` 严禁包含 `ANALYZE` 或 `EXECUTE` 等伴随真实写操作的危险修饰符；
6. **空集合返回契约**：查询列表无匹配数据时统一返回空列表 `[]`，严禁返回 `None`。

---

## 4. Pull Request 流程

- 发起 PR 时，请按模版完整填写变更说明、解决的问题及关联 Issue（如 `close #12`）；
- 确保 CI 流水线（PR 标题语义检查与测试门禁）全部处于绿灯状态；
- 代码审查（Code Review）通过后，由 Maintainer 执行 Squash and Merge 合并到 `main` 分支。

---

## 5. 自动化版本发版与更新日志

本项目**不维护任何静态的物理 `CHANGELOG.md` 文件**（严禁手动创建或提交该文件），全量更新日志与发版说明 100% 由 [git-cliff](https://github.com/orhun/git-cliff) 基于 Git Commit 历史自动生成：

1. **本地即时预览（无需安装）**：
   本地开发者若需在控制台查看当前或历史全量更新日志，可直接借助 `uvx` 即时运行：
   ```bash
   # 预览全量版本历史日志
   uvx git-cliff

   # 仅提取最新版本的发版笔记
   uvx git-cliff --latest --strip header
   ```
2. **触发全渠道自动化发版**：打上符合语义化版本规范的 Git Tag 并推送到仓库：
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```
3. **自动化流水线动作**：
   - GitHub Actions 自动通过 `git-cliff` 提取版本发布笔记；
   - 自动构建标准 Wheel 与 Sdist 并发布到 **PyPI** 官方索引；
   - 自动构建多架构 Docker 镜像并推送至 **GHCR (`ghcr.io`)**；
   - 自动在 **GitHub Releases** 页面挂载打包附件与发布日志。
