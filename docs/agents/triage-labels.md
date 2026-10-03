# 分诊标签字典 (Triage Labels)

智能体工程技能体系基于五个规范的分诊角色推进。本文件定义这五个角色与本仓库工单系统实际标签的映射关系。

| 技能规范角色名 (mattpocock/skills) | 本仓库工单系统标签 | 语义与职责 |
| :--------------------------------- | :----------------- | :--------- |
| `needs-triage` | `needs-triage` | 待维护者评估与分诊 |
| `needs-info` | `needs-info` | 等待反馈者补充必要信息 |
| `ready-for-agent` | `ready-for-agent` | 需求与技术规范完备，可交由 AI Agent 自动实现 |
| `ready-for-human` | `ready-for-human` | 复杂度高或需权限决策，需人类工程师介入与实现 |
| `wontfix` | `wontfix` | 不予处理 / 关闭 |

当技能指示使用某个角色标签时（例如“应用就绪分诊标签”），请使用上表中对应的标签字符串。
