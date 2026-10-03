# 工单追踪系统：GitHub (Issue tracker: GitHub)

本仓库的需求规格与工单统一记录在 GitHub Issues 中。所有交互操作均使用 `gh` 命令行工具完成。

## 约定与操作指令 (Conventions)

- **创建工单**：`gh issue create --title "..." --body "..."`。若为多行正文内容，优先使用 Heredoc 语法。
- **读取工单**：`gh issue view <编号> --comments`，可通过 `jq` 过滤评论并提取标签。
- **列出工单**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，可附加 `--label` 和 `--state` 进行过滤。
- **评论工单**：`gh issue comment <编号> --body "..."`
- **添加 / 移除标签**：`gh issue edit <编号> --add-label "..."` / `--remove-label "..."`
- **关闭工单**：`gh issue close <编号> --comment "..."`

仓库地址通过本地 Git 配置 `git remote -v` 自动推导，在仓库克隆目录下运行 `gh` 会自动定位。

## Pull Requests 作为分诊对象 (Pull requests as a triage surface)

**PRs as a request surface: no.** *(若后续希望将外部 PR 作为需求分诊对象，可将其修改为 `yes`；`/triage` 技能会读取此标志)*

当设置为 `yes` 时，外部 PR 将复用相同的标签与状态流转体系，使用对应的 `gh pr` 指令：

- **读取 PR**：`gh pr view <编号> --comments` 以及 `gh pr diff <编号>` 获取代码差异。
- **列出待分诊外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，仅保留作者关联度 (`authorAssociation`) 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的 PR（排除 `OWNER`/`MEMBER`/`COLLABORATOR`）。
- **评论 / 标签 / 关闭**：对应使用 `gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

由于 GitHub 的 Issue 和 PR 共享同一个数字编号空间，单独的 `#42` 可能为 PR 或 Issue，解析时优先尝试 `gh pr view 42`，若非 PR 则降级回退至 `gh issue view 42`。

## 当技能提示“发布到工单系统”时 (When a skill says "publish to the issue tracker")

执行 `gh issue create` 创建新的 GitHub Issue。

## 当技能提示“获取相关工单”时 (When a skill says "fetch the relevant ticket")

执行 `gh issue view <编号> --comments` 获取工单内容及评论上下文。

## 探路者拓扑操作 (Wayfinding operations)

用于 `/wayfinder` 技能。其中**主路线图 (Map)** 为单一 Issue，各**子工单 (Child tickets)** 作为具体执行任务。

- **主路线图 (Map)**：带有 `wayfinder:map` 标签的单个 Issue，正文包含备忘、既定决策及迷雾区。创建命令：`gh issue create --label wayfinder:map`。
- **子任务工单 (Child ticket)**：通过 GitHub sub-issue 关联到主图（通过 `gh api` 访问子工单端点）；若未开启原生子工单特性，则在主路线图正文的任务列表中列出，并在子工单正文顶部标注 `Part of #<主图编号>`。标签规范：`wayfinder:<类型>`（`research` / `prototype` / `grilling` / `task`）。一旦被认领，该工单将被指派给主导开发者。
- **阻塞依赖关系 (Blocking)**：采用 GitHub 原生工单依赖机制表达。添加依赖关联：`gh api --method POST repos/<所有者>/<仓库名>/issues/<子工单编号>/dependencies/blocked_by -F issue_id=<阻塞工单数据库ID>`（其中 ID 为数字类型的数据库内部 ID：`gh api repos/<所有者>/<仓库名>/issues/<编号> --jq .id`，非 issue 编号或 node_id）。若原生依赖不可用，在子工单顶部标注 `Blocked by: #<编号>, #<编号>`。当所有阻塞工单关闭后，任务自动解锁。
- **前沿就绪查询 (Frontier query)**：列出主图下所有开启中的子任务，剔除存在未关闭阻塞依赖或已有负责人的工单，按主图排布顺序取首个就绪任务。
- **任务认领 (Claim)**：`gh issue edit <编号> --add-assignee @me`。
- **任务解决与沉淀 (Resolve)**：`gh issue comment <编号> --body "<结论>"`，然后 `gh issue close <编号>`，最后将决策要点与超链接追加至主图的“既定决策”段落中。
