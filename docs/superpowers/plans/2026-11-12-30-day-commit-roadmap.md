# 30 天真实提交路线图

**周期：** 2026-11-13 至 2026-12-12

**节奏：** 每天 16:00 和 22:00 各安排一个开发会话，每个会话准备 1 个独立、可解释、通过验证的提交；当天最多 2 个真实提交。GitHub 活跃记录来自 commit，不需要为每个提交单独 push。
**约束：** 不创建空提交、不回填日期、不提交未通过约定验证的代码；当天未完成的提交顺延，不用占位提交补数量。

每个提交必须满足：

1. 只包含一个可描述的行为变化。
2. 对应测试与实现放在同一绿色提交，或该提交本身只改变不影响运行的文档。
3. 提交前检查 `git diff --check` 和目标测试。
4. 16:00 会话完成 Commit A，22:00 会话完成 Commit B；每次提交和 push 前都先展示摘要并获得确认。

## 每日计划

| Day / 日期 | 16:00 Commit A | 22:00 Commit B | 当日验证 |
|---|---|---|---|
| 1 / 11-13 | `fix: restore the cross-platform test baseline`：显式 UTF-8 读取并澄清合成评测来源 | `ci: test the project on windows and linux`：增加跨平台 CI 与合约测试 | `python -m unittest discover -s tests -v` |
| 2 / 11-14 | `build: add installable python project metadata`：增加 `pyproject.toml` 和安装测试 | `feat: add the environment doctor command`：实现 `doctor`、退出码和安装说明 | `python -m unittest tests.test_cli tests.test_public_release -v` |
| 3 / 11-15 | `feat: review local diffs from the command line`：支持文件和 stdin | `feat: emit stable structured review output`：JSON 输出、错误合约和测试 | `python -m unittest tests.test_cli -v` |
| 4 / 11-16 | `build: define the github action contract`：Action 输入、输出和权限测试 | `feat: run the review cli from github actions`：执行 CLI 并上传 artifact | `python -m unittest tests.test_public_release -v` |
| 5 / 11-17 | `docs: promote github app installation`：推荐 App 接入并说明最小权限 | `feat: diagnose github integration capabilities`：doctor 配置检查和失败测试 | `python -m unittest tests.test_cli tests.test_github -v` |
| 6 / 11-18 | `feat: add immutable change set models`：SHA、文件变化和序列化测试 | `feat: add stable review group identities`：`ReviewGroup` 与稳定 ID | `python -m unittest tests.test_review_planner -v` |
| 7 / 11-19 | `feat: filter non-reviewable repository files`：binary/vendor/generated/lock | `feat: match changed source files with tests`：源码测试关联和路径边界测试 | `python -m unittest tests.test_review_planner -v` |
| 8 / 11-20 | `feat: group small changes deterministically`：小 PR 合并与覆盖测试 | `feat: partition large changes by module and language`：大 PR 分组与 exactly-once 守卫 | `python -m unittest tests.test_review_planner -v` |
| 9 / 11-21 | `feat: enforce per-group token budgets`：预算计算和边界测试 | `feat: split oversized groups with deterministic fallback`：拆分、模型失败回退 | `python -m unittest tests.test_review_planner tests.test_context_manager -v` |
| 10 / 11-22 | `feat: add auditable context items`：reason/hash/token 和序列化 | `feat: build bounded deduplicated context bundles`：优先级裁剪与 hash 去重 | `python -m unittest tests.test_review_context -v` |
| 11 / 11-23 | `feat: extract enclosing python symbols`：函数、类和异常语法测试 | `feat: collect python import and call context`：调用关系与相关测试 | `python -m unittest tests.test_review_context -v` |
| 12 / 11-24 | `feat: add the structural analyzer protocol`：语言无关接口和文本回退 | `feat: analyze javascript and typescript context`：Tree-sitter、错误语法降级 | `python -m unittest tests.test_review_context -v` |
| 13 / 11-25 | `feat: analyze go repository context`：Go 符号和 import | `feat: select related controls across languages`：配置、依赖和未知语言测试 | `python -m unittest tests.test_review_context tests.test_store_resources -v` |
| 14 / 11-26 | `refactor: isolate review worker execution`：迁移 Worker 并保持旧 API | `refactor: introduce the staged review pipeline`：Planner→Worker→Gate 和对等测试 | `python -m unittest tests.test_reviewer tests.test_lead_worker_collaboration -v` |
| 15 / 11-27 | `feat: execute review groups concurrently`：有界并发和失败隔离 | `feat: checkpoint partial review progress`：组级恢复和成功结果保留 | `python -m unittest tests.test_lead_worker_collaboration tests.test_runtime_memory_context -v` |
| 16 / 11-28 | `feat: add structured verification verdicts`：确认/不确定/拒绝 | `feat: validate finding reachability and evidence`：head SHA 行号与弱证据过滤 | `python -m unittest tests.test_falsifier -v` |
| 17 / 11-29 | `feat: search repository counterevidence`：已有保护和不可达路径 | `feat: calibrate severity from verified impact`：严重级别与反例测试 | `python -m unittest tests.test_falsifier tests.test_advanced -v` |
| 18 / 11-30 | `feat: derive stable finding identities`：路径、符号和规则规范化 | `feat: prevent evidence fingerprint collisions`：措辞变化与碰撞测试 | `python -m unittest tests.test_finding_reconciler -v` |
| 19 / 12-01 | `feat: reconcile active and resolved findings`：ACTIVE/RESOLVED | `feat: reopen recurring findings safely`：REOPENED、计数和失败保护 | `python -m unittest tests.test_finding_reconciler -v` |
| 20 / 12-02 | `feat: persist sqlite review runs`：head SHA 唯一约束和事务测试 | `feat: persist sqlite finding lifecycles`：状态写入和回滚 | `python -m unittest tests.test_store_resources tests.test_finding_reconciler -v` |
| 21 / 12-03 | `feat: persist postgres review state`：run 与 finding 对等表 | `test: share review store contracts`：SQLite/PostgreSQL 共用合约 | `python -m unittest tests.test_store_resources -v` |
| 22 / 12-04 | `feat: build atomic github review payloads`：inline payload 和身份标记 | `feat: publish line and range comments`：行级、多行和无法定位回退 | `python -m unittest tests.test_publication tests.test_github -v` |
| 23 / 12-05 | `feat: persist hidden comment identities`：评论归属和读取 | `feat: deduplicate findings and suggestions across runs`：双 fingerprint 测试 | `python -m unittest tests.test_publication -v` |
| 24 / 12-06 | `feat: persist publication outbox messages`：事务 Outbox 和状态 | `feat: lease and retry review publications`：退避、DLQ 和防重复测试 | `python -m unittest tests.test_publication tests.test_production_features -v` |
| 25 / 12-07 | `feat: reuse runs for duplicate head shas`：任务级幂等 | `feat: review incrementally from the last successful head`：force-push 安全回退 | `python -m unittest tests.test_incremental_review tests.test_production_features -v` |
| 26 / 12-08 | `feat: add pinned real-pr dataset adapters`：固定 revision 和校验 | `feat: store reproducible per-pr artifacts`：逐样本 verdict 与输入 fingerprint | `python -m unittest tests.test_benchmark_manifest -v` |
| 27 / 12-09 | `feat: compute pull-request bootstrap intervals`：PR 级 95% CI | `feat: report benchmark cost latency and replay commands`：指标与文档 | `python -m unittest tests.test_benchmark_manifest tests.test_agentic_evaluation -v` |
| 28 / 12-10 | `feat: define restricted sandbox policies`：资源、环境和凭据边界 | `feat: run checks in networkless containers`：Docker 与安全降级测试 | `python -m unittest tests.test_sandbox -v` |
| 29 / 12-11 | `feat: capture evidence before repair`：原始快照复现 | `feat: verify repairs with paired sandbox evidence`：after 验证和阻断测试 | `python -m unittest tests.test_sandbox tests.test_production_features -v` |
| 30 / 12-12 | `docs: publish architecture and interview demos`：架构、幂等、反证、沙箱演示 | `release: prepare the evidence-first preview`：版本、变更记录和全量验证 | `python -m unittest discover -s tests -v; python -m compileall -q evoagent scripts tests` |

## 每日操作模板

```powershell
git status --short
python -m unittest <当天目标测试> -v
git diff --check
git add <当天当前提交涉及的精确文件>
git diff --cached --stat
git commit -m "<计划中的英文 message>"
```

当天两个候选提交完成后：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q evoagent scripts tests
git log -2 --oneline
git status --short
```

确认测试结果和提交摘要后，再执行一次：

```powershell
git push origin <当前功能分支>
```

## PR 组织策略

不按每天两个 PR 拆分。60 个碎片 PR 会削弱审查质量，也不利于面试官理解演进过程。两个每日提交按依赖聚合为 8 个可独立审查的 PR，使默认分支每 2–5 天获得一次稳定更新：

1. Days 1–5：安装、CLI、Action 与 GitHub App 接入。
2. Days 6–9：Change Planner、确定性分组与 Token 预算。
3. Days 10–13：ContextBundle 与 Python、JavaScript/TypeScript、Go 上下文分析。
4. Days 14–17：分阶段 Pipeline、并发恢复与 Falsifier。
5. Days 18–21：Finding 生命周期与双数据库持久化。
6. Days 22–25：inline Review、去重、Outbox 与增量审查。
7. Days 26–27：真实 Benchmark、置信区间、成本与重放证据。
8. Days 28–30：Sandbox、配对修复证据、演示与 Preview Release。

每个阶段结束后创建 PR，附带变更摘要、测试结果、风险和演示步骤。检查通过后使用普通 merge commit 合并，保留阶段内的每日 commit；随后从最新 `main` 继续下一阶段。不得使用 squash、force push 或历史重写。这样功能分支保留审查边界，默认分支的最近维护时间最长不会超过 5 天。

## 每周面试材料产出

- 第 1 周：可安装 CLI、GitHub Action、跨平台 CI；能讲开发者体验和发布工程。
- 第 2 周：Change Planner 与 ContextBundle；能讲确定性流程和 Token 预算。
- 第 3 周：Falsifier 与 Finding 生命周期；能讲 Agent 可靠性和状态建模。
- 第 4 周：inline Review、Outbox、增量审查、真实 Benchmark 和 Sandbox；能讲后端一致性、故障恢复和安全执行。
- 第 30 天：录制三个固定 Demo，并用实际 Benchmark 数据更新简历描述。

## 计划偏差处理

如果某项工作超过一天，保持提交内容真实并顺延后续工作，不使用空提交维持数字。若当天只完成一个绿色提交，贡献记录仍然真实有效；项目质量和可解释性优先于固定提交数量。
