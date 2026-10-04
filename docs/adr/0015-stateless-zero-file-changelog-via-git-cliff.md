# ADR-0015: 彻底废除物理 CHANGELOG.md 并由 git-cliff 实现无状态自动化发版

- **状态**: Accepted
- **日期**: 2026-10-04
- **决定者**: Ateng, 孔余

## 背景与问题陈述 (Context)

在传统的开源项目维护过程中，维护者通常会在仓库根目录保留一个静态的 `CHANGELOG.md` 物理文件，并在每次发版或代码合并时手动更新该文件。
然而，在基于 GitHub Actions 自动化 CI/CD 和规范化提交（Conventional Commits）的现代化工程实践中，这种手写静态物理文件的模式暴露出以下严重缺陷：
1. **多分支并发合并冲突**：多个特性分支或并发 PR 分别修改 `CHANGELOG.md`，极易导致冲突并阻碍合并；
2. **人工维护漏更与心智负担**：维护者容易遗漏关键提交或错误归类；
3. **CI 回写循环污染**：若由 CI 脚本自动生成并 commit 回写仓库，会产生大量非开发人员意图的机器人提交（Bot Commits），破坏干净的 Git 历史甚至引发 CI 递归触发。

## 决策 (Decision)

我们决定**彻底废除并物理删除代码库中的 `CHANGELOG.md` 文件**，全面转向**无状态自动化更新日志架构 (Stateless Zero-File Changelog)**：

1. **物理文件彻底移除**：版本控制系统（Git）中不再追踪任何 `CHANGELOG.md` 物理文件，并在规约中禁止手动创建；
2. **重构 `.cliff.toml` 为标准双层结构**：
   - 外层按发布版本/Tag 进行生命周期渲染（`## [{{ version }}] - {{ timestamp }}`）；
   - 内层按 Conventional Commits 分组（Features, Bug Fixes, Performance, Refactor 等）；
   - 过滤 `^Merge` / `^merge` 纯合并提交，同时宽容收录所有非规范提交至“💼 其他变更 (Other)”；
3. **分发渠道与公共生态闭环导流**：
   - 在 `pyproject.toml` 的 `[project.urls]` 中将 `Changelog` 明确指向 GitHub Releases 页面，PyPI 官方页面直接挂载该外链；
   - 在 `README.md` 徽章区与尾部章节显式引导访问 GitHub Releases；
   - 在 `CONTRIBUTING.md` 中为本地开发者提供免安装即时预览指令 `uvx git-cliff` 与 `--latest --strip header`。

## 结果与影响 (Consequences)

### 正面影响 (Positive)
- **零维护摩擦**：彻底消除人工编辑更新日志的心智负担与分支冲突可能；
- **真实性保障**：更新日志 100% 忠实映射真实的 Git Commit 历史，透明可追溯；
- **全渠道一致体验**：GitHub Releases 页面、PyPI 首页导流与本地 `uvx git-cliff` 预览呈现完全一致的格式与内容。

### 需遵循的约束 (Negative/Trade-offs)
- 团队与贡献者必须严格遵循 Conventional Commits 提交格式规范，以便 `git-cliff` 准确提取变更类别。
