# 30 天真实提交路线图

**周期：** 2026-11-13 至 2026-12-12

**节奏：** 每天计划 3 个独立、可解释、通过验证的提交；当天完成后统一 `git push` 即可。GitHub 活跃记录来自 commit，不需要一天执行三次 push。
**约束：** 不创建空提交、不回填日期、不提交未通过约定验证的代码；当天未完成的提交顺延，不用占位提交补数量。

每个提交必须满足：

1. 只包含一个可描述的行为变化。
2. 对应测试与实现放在同一绿色提交，或该提交本身只改变不影响运行的文档。
3. 提交前检查 `git diff --check` 和目标测试。
4. 每天第三个提交后运行当日验证命令，再向 `origin` push。

## 每日计划

| Day / 日期 | Commit 1 | Commit 2 | Commit 3 | 当日验证 |
|---|---|---|---|---|
| 1 / 11-13 | `fix: read project docs as utf-8`：修复 Windows README 测试 | `docs: distinguish synthetic evaluation results`：澄清 92.5% 数据来源 | `ci: test the project on windows and linux`：增加跨平台 CI | `python -m unittest discover -s tests -v` |
| 2 / 11-14 | `build: add python project metadata`：增加 `pyproject.toml` | `feat: add environment doctor command`：实现并测试 `doctor` | `docs: document editable installation`：增加安装说明 | `python -m unittest tests.test_cli tests.test_public_release -v` |
| 3 / 11-15 | `feat: add local diff review command`：CLI 接收文件和 stdin | `feat: emit structured review json`：稳定 JSON 输出 | `test: cover cli exit status contracts`：补错误输入和退出码 | `python -m unittest tests.test_cli -v` |
| 4 / 11-16 | `build: define the github action contract`：增加 `action.yml` 输入输出 | `feat: run review cli from github actions`：Action 调用 CLI | `test: validate action permissions and defaults`：解析 YAML 合约 | `python -m unittest tests.test_public_release -v` |
| 5 / 11-17 | `docs: promote github app installation`：以 App 为推荐接入 | `feat: report github integration capabilities`：doctor 展示权限和配置 | `test: cover github app setup failures`：缺失配置给出精确错误 | `python -m unittest tests.test_cli tests.test_github -v` |
| 6 / 11-18 | `feat: add immutable change set models`：加入 SHA 和文件变化模型 | `feat: add stable review group identities`：定义 `ReviewGroup` | `test: cover review domain serialization`：序列化稳定性 | `python -m unittest tests.test_review_planner -v` |
| 7 / 11-19 | `feat: filter non-reviewable repository files`：过滤 binary/vendor/generated | `feat: match tests with changed source files`：建立源码测试关联 | `test: cover deterministic file filtering`：大小写和路径边界 | `python -m unittest tests.test_review_planner -v` |
| 8 / 11-20 | `feat: group small changes deterministically`：小 PR 合并策略 | `feat: partition changes by module and language`：大 PR 分组 | `test: enforce exactly-once file coverage`：遗漏和重复守卫 | `python -m unittest tests.test_review_planner -v` |
| 9 / 11-21 | `feat: enforce per-group token budgets`：组级预算 | `feat: split oversized review groups`：稳定拆分 | `test: cover grouping fallback behavior`：模型分组失败回退 | `python -m unittest tests.test_review_planner tests.test_context_manager -v` |
| 10 / 11-22 | `feat: add auditable context items`：记录 reason/hash/token | `feat: build bounded context bundles`：优先级裁剪 | `test: cover context deduplication`：内容 hash 去重 | `python -m unittest tests.test_review_context -v` |
| 11 / 11-23 | `feat: extract enclosing python symbols`：Python AST 定位 | `feat: collect direct python call context`：调用和 import 关系 | `test: cover python context selection`：函数、类和异常语法 | `python -m unittest tests.test_review_context -v` |
| 12 / 11-24 | `feat: add structural analyzer protocol`：语言无关接口 | `feat: add javascript and typescript analyzer`：Tree-sitter 适配 | `test: cover javascript context limits`：错误语法安全降级 | `python -m unittest tests.test_review_context -v` |
| 13 / 11-25 | `feat: add go structural analyzer`：Go 符号和 import | `feat: select related repository controls`：配置和依赖文件 | `test: cover multi-language context fallback`：未知语言文本回退 | `python -m unittest tests.test_review_context tests.test_store_resources -v` |
| 14 / 11-26 | `refactor: isolate review worker execution`：迁移 Worker 调度 | `refactor: introduce staged review pipeline`：Planner→Worker→Gate | `test: preserve legacy reviewer contracts`：旧 API 对等测试 | `python -m unittest tests.test_reviewer tests.test_lead_worker_collaboration -v` |
| 15 / 11-27 | `feat: execute review groups concurrently`：有界并发 | `feat: checkpoint completed review groups`：组级恢复 | `test: preserve partial review results`：单组失败不丢成功结果 | `python -m unittest tests.test_lead_worker_collaboration tests.test_runtime_memory_context -v` |
| 16 / 11-28 | `feat: add structured verification verdicts`：确认/不确定/拒绝 | `feat: validate finding line reachability`：head SHA 行号校验 | `test: cover weak evidence rejection`：证据不足过滤 | `python -m unittest tests.test_falsifier -v` |
| 17 / 11-29 | `feat: search repository counterevidence`：已有保护和不可达路径 | `feat: calibrate severity from verified impact`：严重级别校准 | `test: cover existing mitigation counterexamples`：反例测试 | `python -m unittest tests.test_falsifier tests.test_advanced -v` |
| 18 / 11-30 | `feat: derive stable finding identities`：不依赖标题措辞 | `feat: normalize evidence fingerprints`：路径/符号/证据规范化 | `test: cover finding identity collisions`：碰撞和措辞变化 | `python -m unittest tests.test_finding_reconciler -v` |
| 19 / 12-01 | `feat: reconcile active and resolved findings`：ACTIVE/RESOLVED | `feat: reopen recurring findings`：REOPENED 和计数 | `test: protect state on incomplete reviews`：失败运行不误解决 | `python -m unittest tests.test_finding_reconciler -v` |
| 20 / 12-02 | `feat: persist sqlite review runs`：head SHA 唯一约束 | `feat: persist sqlite finding states`：生命周期存储 | `test: cover sqlite review state transactions`：事务回滚 | `python -m unittest tests.test_store_resources tests.test_finding_reconciler -v` |
| 21 / 12-03 | `feat: persist postgres review runs`：PostgreSQL 对等表 | `feat: persist postgres finding states`：状态对等 | `test: share review store contracts`：共用 Store contract | `python -m unittest tests.test_store_resources -v` |
| 22 / 12-04 | `feat: build github inline review payloads`：原子 Review | `feat: publish line and range comments`：行级、多行评论 | `test: fall back when line mapping fails`：无法定位进入 summary | `python -m unittest tests.test_publication tests.test_github -v` |
| 23 / 12-05 | `feat: embed hidden comment identities`：评论归属标识 | `feat: deduplicate findings across runs`：内容和代码双 fingerprint | `test: cover suggestion comment deduplication`：重复 Suggestion | `python -m unittest tests.test_publication -v` |
| 24 / 12-06 | `feat: persist publication outbox messages`：事务 Outbox | `feat: lease and retry review publications`：租约和退避 | `test: prevent duplicate remote reviews`：fail-once 恢复 | `python -m unittest tests.test_publication tests.test_production_features -v` |
| 25 / 12-07 | `feat: reuse runs for duplicate head shas`：任务级幂等 | `feat: review commits from the last successful head`：增量范围 | `test: fall back safely after force pushes`：不可达 anchor 回退 | `python -m unittest tests.test_incremental_review tests.test_production_features -v` |
| 26 / 12-08 | `feat: add pinned real-pr dataset adapters`：固定数据 revision | `feat: store per-pr benchmark artifacts`：逐样本 verdict | `test: fingerprint benchmark inputs`：模型/Prompt/Skill hash | `python -m unittest tests.test_benchmark_manifest -v` |
| 27 / 12-09 | `feat: compute pull-request bootstrap intervals`：95% CI | `feat: report benchmark cost and latency`：成本与耗时 | `docs: publish reproducible benchmark commands`：重放说明 | `python -m unittest tests.test_benchmark_manifest tests.test_agentic_evaluation -v` |
| 28 / 12-10 | `feat: define restricted sandbox policies`：资源和环境边界 | `feat: run checks in networkless containers`：无网络容器 | `test: degrade safely without docker`：降级为 Suggestion | `python -m unittest tests.test_sandbox -v` |
| 29 / 12-11 | `feat: capture before repair evidence`：修复前复现 | `feat: verify repair evidence in the sandbox`：修复后验证 | `test: block fixes without paired evidence`：缺证据禁止发分支 | `python -m unittest tests.test_sandbox tests.test_production_features -v` |
| 30 / 12-12 | `docs: publish the platform architecture`：架构与决策记录 | `docs: add three interview demo scenarios`：幂等、反证、沙箱演示 | `release: prepare the evidence-first preview`：版本、变更记录和最终验证 | `python -m unittest discover -s tests -v; python -m compileall -q evoagent scripts tests` |

## 每日操作模板

```powershell
git status --short
python -m unittest <当天目标测试> -v
git diff --check
git add <当天当前提交涉及的精确文件>
git diff --cached --stat
git commit -m "<计划中的英文 message>"
```

一天三个提交完成后：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q evoagent scripts tests
git log -3 --oneline
git status --short
```

确认测试结果和提交摘要后，再执行一次：

```powershell
git push origin <当前功能分支>
```

## 每周面试材料产出

- 第 1 周：可安装 CLI、GitHub Action、跨平台 CI；能讲开发者体验和发布工程。
- 第 2 周：Change Planner 与 ContextBundle；能讲确定性流程和 Token 预算。
- 第 3 周：Falsifier 与 Finding 生命周期；能讲 Agent 可靠性和状态建模。
- 第 4 周：inline Review、Outbox、增量审查、真实 Benchmark 和 Sandbox；能讲后端一致性、故障恢复和安全执行。
- 第 30 天：录制三个固定 Demo，并用实际 Benchmark 数据更新简历描述。

## 计划偏差处理

如果某项工作超过一天，保持提交内容真实并顺延后续工作，不使用空提交维持数字。若当天只完成两个绿色提交，贡献记录仍然真实有效；项目质量和可解释性优先于固定提交数量。
