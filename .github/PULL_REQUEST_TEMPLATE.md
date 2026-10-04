## 变更说明
<!-- 请简要说明此 PR 解决的问题、新增的特性或改动的背景 -->

## 关联 Issue
- 修复/关联: close #

## 变更类型
<!-- 请在符合项的括号内填入 x，例如 [x] -->
- [ ] `feat`: 新增功能或扩展新数据库方言
- [ ] `fix`: 缺陷修复
- [ ] `docs`: 文档变动
- [ ] `style`: 代码格式调整（不影响业务逻辑）
- [ ] `refactor`: 代码重构（非新功能、非修复）
- [ ] `perf`: 性能优化
- [ ] `test`: 补全或重构单元测试
- [ ] `build`: 构建配置、依赖调整
- [ ] `ci`: GitHub Actions 流水线或部署变动
- [ ] `chore`: 其他杂项与工程维护

## 架构自检清单
- [ ] 提交信息符合 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范
- [ ] 所有数据库同步 I/O 均通过 `anyio.to_thread.run_sync` 异步卸载
- [ ] 查询无数据返回时统一返回空列表 `[]`（无 None 污染）
- [ ] 本地已运行 `uv run ruff check` 并全部通过
- [ ] 本地已运行 `uv run pytest -s` 且全量单测通过
- [ ] 如涉及 API 或配置变更，已同步更新相关文档与注释
