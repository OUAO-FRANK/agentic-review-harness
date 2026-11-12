# Evidence-First Review Platform 设计规格

**状态：** 待用户审查

**日期：** 2026-11-12
**目标读者：** Agent 开发、后端开发与代码审查方向的面试官和贡献者

## 1. 目标

把 Agentic Review Harness 升级为一个证据驱动、可评测、可恢复的 PR Review Agent 平台，同时展示两类工程能力：

- Agent 工程：变化规划、上下文构建、专长 Worker、反证验证、结构化输出、Token/成本预算与离线评测。
- 后端工程：GitHub App、Webhook 幂等、持久队列、checkpoint、增量审查、Outbox 发布、SQLite/PostgreSQL 一致性和可观测性。

项目不以功能数量取胜，而以以下闭环作为核心差异：

```text
计划审查范围 → 收集仓库证据 → 生成候选 Finding → 主动寻找反例
→ 合并和校准 → 发布行级 Review → 根据新提交和反馈更新状态
```

## 2. 非目标

- 30 天内不重写为 Go。
- 30 天内不新增 GitLab、Bitbucket、Gitea 集成。
- 不继续增加固定 Agent 角色数量。
- 不先重做管理台视觉界面。
- 不用合成 fixture 的结果宣称真实 PR 准确率。
- 不制造空提交、回填提交日期或自动提交未经验证的代码。

## 3. 当前基线

当前仓库已经具备 Lead/Worker/Critic、Skill、证据门禁、checkpoint、SQLite/PostgreSQL、Redis 队列、GitHub App 认证、Webhook delivery 幂等、DLQ、修复验证和评测框架。

需要重点补齐的缺口：

1. `evoagent/agentic_core.py` 同时负责规划、执行、协作、合并和验证，边界过大。
2. 审查输入主要围绕完整 Diff，没有显式 `ReviewGroup` 和可审计的 `ContextBundle`。
3. GitHub 仅更新汇总 Issue Comment，没有原子行级 Review、Suggestion 和跨运行 Finding 状态。
4. 已有 Webhook 幂等，但没有 Review Run 唯一键和可靠发布 Outbox。
5. Python 使用 AST，其他语言缺少统一的结构化上下文接口。
6. 评测 fixture 适合回归测试，但缺少真实 PR Benchmark、逐样本产物和置信区间。
7. 临时 checkout 不是进程级安全沙箱。
8. 缺少 `pyproject.toml`、CLI、官方 Action、跨平台 CI、Release 和清晰的开源授权。

2026-11-12 的 Windows 基线为 79 个测试中 78 个通过、1 个失败；失败来自 `tests/test_public_release.py` 未显式使用 UTF-8 读取中文 README。该问题作为第一项修复，不掩盖为新改动导致的失败。

## 4. 参考项目与吸收边界

### OpenCodeReview

吸收：确定性文件选择、相关文件分组、规则按路径匹配、组级 Token 阀门、Session Resume、独立定位和反思阶段。

边界：只吸收设计思想，不复制其 Go 实现；继续使用本项目 Python 技术栈。

### PR-Agent

吸收：Git Provider 边界、增量锚点、隐藏评论身份、跨运行去重、Finding 状态协调、模型 fallback 和大 PR 分块。

边界：第一阶段仅实现 GitHub，不复制多平台复杂度和大规模配置矩阵。

### PR-AF、reviewdog、OpenReview

- PR-AF：Evidence Grounding 与 Falsifiability Gate。
- reviewdog：Provider-neutral Diagnostic/Reporter 思想。
- OpenReview：隔离执行、Suggestion 和人工反馈闭环。

所有借鉴在 README 的 `Acknowledgements` 中说明；若未来直接移植源码，必须逐文件确认许可证并保留要求的版权声明。

## 5. 目标架构

```text
GitHub Webhook / CLI / GitHub Action
                │
                ▼
          ReviewService
     签名、授权、幂等、限流
                │
                ▼
        ReviewOrchestrator
   状态机、租约、重试、checkpoint
                │
                ▼
          ChangePlanner
  文件过滤、风险评分、关联分组、预算
                │
                ▼
         ContextBuilder
 Diff、符号、依赖、测试、配置、来源
                │
                ▼
       ReviewPipeline
  Lead → 并行 Workers → Falsifier → Lead
                │
                ▼
       FindingReconciler
  身份、去重、ACTIVE/RESOLVED/REOPENED
                │
                ▼
        PublicationOutbox
  GitHub Review、inline comment、summary
                │
                ▼
     Evaluation / Trace / Feedback
```

## 6. 核心领域模型

### ChangeSet

记录 `repository`、`pull_request`、`base_sha`、`head_sha`、结构化文件变化和来源。相同 `repository + pull_request + head_sha + mode` 只能存在一个有效 Review Run。

### ReviewGroup

一组应共同审查的文件和 hunk，包含分组理由、风险标签、规则集合、Token 预算和稳定的 `group_id`。规划器必须保证每个可审查文件恰好归属一个组。

### ContextBundle

每条上下文必须记录：路径、行范围、内容、选择原因、选择工具、Token 数量和内容 hash。Worker 只能看到分配给自己的 group、Skill 和 ContextBundle。

### FindingCandidate 与 VerifiedFinding

候选 Finding 先表达 claim，再由 Falsifier 记录 supporting evidence、attempted counterexample、uncertainty 和 verdict。只有通过验证的 Finding 才进入发布阶段。

### FindingState

状态为 `ACTIVE`、`RESOLVED`、`REOPENED`。Finding ID 基于仓库、规则、路径、符号和规范化证据生成，不依赖可变的自然语言标题。

## 7. 审查模式

### fast

- 确定性文件分组。
- 每组一个专长 Worker。
- 轻量 Falsifier。
- 不执行不可信仓库命令。
- 面向常规 PR 和低延迟反馈。

### deep

- 风险驱动的多 Worker 协作。
- 跨文件 ContextBundle。
- 完整反证、严重级别校准。
- 在 Docker 沙箱中运行允许的检查。
- 满足修复前后证据后才允许创建修复分支。

## 8. GitHub 集成

- Webhook delivery 保持 payload-bound 幂等。
- Review Run 增加 head SHA 唯一性，重复 delivery 返回既有任务。
- 使用 Pull Request Review API 原子发布 inline comments。
- 评论中嵌入不可见 identity 和 finding fingerprint。
- 新 head SHA 到达时，只审查新增提交并协调既有 Finding 状态。
- Outbox 在数据库事务中保存待发布消息；远端 API 失败可重试而不会重复评论。
- 汇总评论展示 Review 模式、覆盖文件、成本、耗时、失败 group 和 Finding 状态变化。

## 9. 安全边界

- Webhook 和 GitHub App 私钥沿用现有最小权限设计。
- 默认不执行 PR 中的代码。
- deep 模式命令运行在无网络、非 root、资源受限的 Docker 容器。
- 模型密钥、GitHub token 和数据库凭据不进入沙箱。
- 自动修复只针对允许路径；没有 before/after 证据时降级为 Suggestion。
- 外部内容视为不可信数据，不允许覆盖系统指令和工具权限。

## 10. 评测设计

评测分三层：

1. Synthetic regression：稳定验证解析、规则、状态机和门禁。
2. Real PR benchmark：接入公开真实 PR 数据，统计 Precision、Recall、F1/F2 和定位正确率。
3. Online feedback：统计接受、拒绝、解决、重新出现和人工 dismiss reason。

每次 Benchmark 生成不可变 Manifest，至少包括 git SHA、模型版本、Prompt/Skill/Dataset fingerprint、逐 PR 结果、Token、成本、耗时和错误。对 PR 维度执行 bootstrap，输出 95% 置信区间。

需要至少完成以下消融：单 Agent、无仓库上下文、无 Falsifier、无 Critic、完整流水线。项目只陈述实际测得结果，不预设多 Agent 优于单 Agent。

## 11. 后端可靠性

- `webhook_deliveries`：保留现有 delivery 幂等。
- `review_runs`：保存 head SHA、模式、状态和唯一键。
- `finding_states`：保存跨运行 Finding 生命周期。
- `publication_outbox`：保存待发布 Review，支持租约、重试和 DLQ。
- SQLite 和 PostgreSQL 必须通过同一 store contract 测试。
- trace 使用 `task_id`、`run_id`、`group_id` 和 `delivery_id` 关联。

## 12. 验收标准

- Windows 和 Linux CI 全部通过；所有文本读取显式使用 UTF-8。
- `pip install -e .` 后可运行 `agentic-review doctor`、`agentic-review serve` 和 `agentic-review review`。
- 同一 Webhook delivery 不生成重复任务；同一 head SHA 不生成重复 Review Run。
- 同一 Finding 在跨运行时保持稳定 ID，并能进入 RESOLVED 和 REOPENED。
- GitHub 一轮审查以一个 Review 原子发布，不重复 inline comment。
- Planner 对所有可审查文件实现一次且仅一次覆盖，并在模型失败时确定性回退。
- 每条发布 Finding 都带证据和反证结果。
- 真实 PR Benchmark 可从固定 Manifest 重放，逐样本结果公开。
- 不可信测试命令只能在资源受限、无凭据的沙箱中运行。

## 13. 30 天交付边界

30 天交付覆盖基础工程、变化规划、上下文、流水线拆分、反证、Finding 生命周期、GitHub inline 发布、增量审查、真实评测适配和最小 Docker 沙箱。多 Git 平台、完整组织管理后台和大规模向量检索留在 30 天范围之外。
