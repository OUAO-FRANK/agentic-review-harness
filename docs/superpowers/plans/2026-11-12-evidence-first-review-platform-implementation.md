# Evidence-First Review Platform 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将现有 PR 多 Agent 审查服务升级为具备确定性变化规划、证据反证、跨运行 Finding 状态、GitHub inline review、真实评测和安全执行能力的平台。

**架构：** 保留现有 ReviewService、AgentRuntime 和 Store，通过小型领域对象将 Planner、Context、Workers、Falsifier、Reconciler 和 Publisher 分离。LLM 只承担动态判断，覆盖完整性、预算、状态、幂等和发布由确定性代码保证。

**技术栈：** Python 3.11、unittest、SQLite/PostgreSQL、Redis Streams、GitHub REST API、OpenTelemetry、Tree-sitter、Docker。

---

## 文件结构

**创建：**

- `pyproject.toml`：安装元数据、CLI entry point 和测试配置。
- `evoagent/cli.py`：`doctor`、`serve`、`review` 命令。
- `evoagent/review/types.py`：ChangeSet、ReviewGroup、ContextBundle、VerifiedFinding。
- `evoagent/review/planner.py`：文件过滤、分组、风险与预算。
- `evoagent/review/context.py`：结构化上下文选择和 Token 预算。
- `evoagent/review/workers.py`：组级 Worker 调度。
- `evoagent/review/falsifier.py`：证据与反证校验。
- `evoagent/review/reconciler.py`：Finding ID 和生命周期协调。
- `evoagent/review/pipeline.py`：阶段编排与 checkpoint。
- `evoagent/publication.py`：Review payload、Outbox 和重试发布。
- `evoagent/benchmark.py`：真实 PR 数据适配和 Manifest。
- `evoagent/sandbox.py`：Docker 沙箱命令构造与执行边界。
- `action.yml`：官方 GitHub Action 入口。
- `.github/workflows/ci.yml`：Windows/Linux 基线验证。
- `tests/test_cli.py`、`tests/test_review_planner.py`、`tests/test_review_context.py`、`tests/test_falsifier.py`、`tests/test_finding_reconciler.py`、`tests/test_publication.py`、`tests/test_incremental_review.py`、`tests/test_benchmark_manifest.py`、`tests/test_sandbox.py`。

**修改：**

- `evoagent/agentic_core.py`：把阶段实现迁移到专用模块，保留兼容入口。
- `evoagent/github.py`：增加 GitHub Review、评论读取和发布确认接口。
- `evoagent/models.py`：引用新领域类型，保留已有 Finding 序列化兼容性。
- `evoagent/service.py`：创建唯一 Review Run、调用新 Pipeline、写入 Outbox。
- `evoagent/store.py`、`evoagent/postgres_store.py`：新增 review_runs、finding_states、publication_outbox。
- `evoagent/task_queue.py`：接入发布任务的租约和 DLQ。
- `evoagent/repository_tools.py`：向 ContextBuilder 提供语言无关 Analyzer 接口。
- `evoagent/verifier.py`、`evoagent/patching.py`：将不可信命令切换到 SandboxRunner。
- `README.md`：真实描述评测来源、安装、Action 和架构。

### 任务 1：恢复跨平台绿色基线并建立安装入口

**文件：**
- 创建：`pyproject.toml`
- 创建：`evoagent/cli.py`
- 创建：`.github/workflows/ci.yml`
- 修改：`tests/test_public_release.py`
- 测试：`tests/test_cli.py`

- [ ] **步骤 1：修复 UTF-8 基线测试**

把 README 读取改为显式编码：

```python
readme = (ROOT / "README.md").read_text(encoding="utf-8")
```

运行：`python -m unittest tests.test_public_release -v`

预期：`OK`。

- [ ] **步骤 2：增加安装元数据和最小 CLI 测试**

```python
def test_doctor_returns_zero_for_local_provider(self):
    code = main(["doctor"], environ={"EVOAGENT_LLM_PROVIDER": "local"})
    self.assertEqual(0, code)
```

`pyproject.toml` 注册：

```toml
[project.scripts]
agentic-review = "evoagent.cli:entrypoint"
```

运行：`python -m unittest tests.test_cli -v`

预期：CLI 测试通过。

- [ ] **步骤 3：增加 Windows/Linux CI**

CI 固定执行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q evoagent scripts tests
```

本地运行同样命令，预期全部通过。

- [ ] **步骤 4：提交**

```bash
git add pyproject.toml evoagent/cli.py tests/test_cli.py tests/test_public_release.py .github/workflows/ci.yml
git commit -m "build: add cross-platform project entrypoints"
```

### 任务 2：建立变化规划领域模型

**文件：**
- 创建：`evoagent/review/__init__.py`
- 创建：`evoagent/review/types.py`
- 创建：`evoagent/review/planner.py`
- 测试：`tests/test_review_planner.py`

- [ ] **步骤 1：编写一次且仅一次覆盖测试**

```python
def test_planner_covers_each_reviewable_file_once(self):
    change = ChangeSet.from_diff(REPRESENTATIVE_DIFF, "base", "head")
    groups = ChangePlanner(max_files=2, max_tokens=500).plan(change)
    paths = [path for group in groups for path in group.paths]
    self.assertEqual(sorted(set(paths)), sorted(paths))
    self.assertEqual({"src/a.py", "src/b.py", "tests/test_a.py"}, set(paths))
```

- [ ] **步骤 2：实现不可变领域对象**

```python
@dataclass(frozen=True)
class ReviewGroup:
    group_id: str
    paths: tuple[str, ...]
    reason: str
    risk_tags: tuple[str, ...]
    token_budget: int
```

- [ ] **步骤 3：实现确定性 fallback 分组**

按目录、语言和测试关联分组；排除 binary、vendor、generated 和 lock 文件。相同输入必须产生相同 `group_id`。

运行：`python -m unittest tests.test_review_planner -v`

预期：覆盖、预算、排除和稳定性测试全部通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/review tests/test_review_planner.py
git commit -m "feat: add deterministic change planner"
```

### 任务 3：构建可审计的 ContextBundle

**文件：**
- 创建：`evoagent/review/context.py`
- 修改：`evoagent/repository_tools.py`
- 测试：`tests/test_review_context.py`

- [ ] **步骤 1：编写来源和预算测试**

```python
def test_context_records_reason_and_respects_budget(self):
    bundle = builder.build(group, token_budget=240)
    self.assertLessEqual(bundle.total_tokens, 240)
    self.assertTrue(all(item.reason and item.content_hash for item in bundle.items))
```

- [ ] **步骤 2：定义 Analyzer 接口**

```python
class RepositoryAnalyzer(Protocol):
    def enclosing_symbol(self, path: str, line: int) -> ContextItem | None: ...
    def related_symbols(self, path: str, symbol: str) -> list[ContextItem]: ...
    def related_tests(self, path: str, symbol: str) -> list[ContextItem]: ...
```

- [ ] **步骤 3：实现优先级裁剪**

优先级固定为变更符号、直接依赖、直接调用者、相关测试、项目控制文件。裁剪时保留选择理由和内容 hash。

运行：`python -m unittest tests.test_review_context -v`

预期：预算不超限，重复内容按 hash 去重。

- [ ] **步骤 4：提交**

```bash
git add evoagent/review/context.py evoagent/repository_tools.py tests/test_review_context.py
git commit -m "feat: add auditable repository context bundles"
```

### 任务 4：拆分组级 Pipeline 并保留 checkpoint

**文件：**
- 创建：`evoagent/review/workers.py`
- 创建：`evoagent/review/pipeline.py`
- 修改：`evoagent/agentic_core.py`
- 修改：`evoagent/service.py`
- 测试：`tests/test_lead_worker_collaboration.py`

- [ ] **步骤 1：增加部分失败测试**

```python
def test_group_failure_preserves_successful_group_results(self):
    result = pipeline.run(change_set, fail_groups={"group-b"})
    self.assertEqual("PARTIAL", result.status)
    self.assertEqual(["group-a"], result.completed_groups)
    self.assertEqual(["group-b"], result.failed_groups)
```

- [ ] **步骤 2：实现阶段接口**

```python
class ReviewPipeline:
    def run(self, task_id: str, change_set: ChangeSet) -> PipelineResult:
        groups = self.planner.plan(change_set)
        candidates = self.workers.review(groups)
        verified = self.falsifier.verify(candidates)
        return self.reconciler.reconcile(task_id, verified)
```

- [ ] **步骤 3：迁移兼容入口**

`AgenticReviewer.review_with_context()` 暂时委托新 Pipeline，原公共方法和报告字段保持兼容；每个 group 完成后写 checkpoint。

运行：`python -m unittest tests.test_lead_worker_collaboration tests.test_runtime_memory_context -v`

预期：旧协作和恢复测试继续通过，新部分失败测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/review evoagent/agentic_core.py evoagent/service.py tests/test_lead_worker_collaboration.py
git commit -m "refactor: isolate the grouped review pipeline"
```

### 任务 5：增加 Evidence Falsifier

**文件：**
- 创建：`evoagent/review/falsifier.py`
- 修改：`evoagent/gates.py`
- 测试：`tests/test_falsifier.py`

- [ ] **步骤 1：编写已有保护反例测试**

```python
def test_falsifier_rejects_claim_when_caller_already_validates(self):
    verdict = falsifier.verify(candidate, context_with_validation)
    self.assertEqual("REJECTED", verdict.status)
    self.assertEqual("existing-mitigation", verdict.reason)
```

- [ ] **步骤 2：实现结构化 verdict**

```python
@dataclass(frozen=True)
class VerificationVerdict:
    status: str
    supporting_evidence: tuple[EvidenceRef, ...]
    attempted_counterexample: str
    uncertainty: str
    reason: str
```

- [ ] **步骤 3：接入 FindingGate**

只有 `CONFIRMED` 进入发布；`UNCERTAIN` 留在 trace，不作为 GitHub inline comment；`REJECTED` 记录过滤原因。

运行：`python -m unittest tests.test_falsifier tests.test_advanced -v`

预期：反例、弱证据和严重级别校准测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/review/falsifier.py evoagent/gates.py tests/test_falsifier.py
git commit -m "feat: verify findings against counterevidence"
```

### 任务 6：持久化 Finding 生命周期

**文件：**
- 创建：`evoagent/review/reconciler.py`
- 修改：`evoagent/store.py`
- 修改：`evoagent/postgres_store.py`
- 测试：`tests/test_finding_reconciler.py`
- 测试：`tests/test_store_resources.py`

- [ ] **步骤 1：编写稳定身份测试**

```python
def test_wording_change_keeps_same_finding_id(self):
    left = finding(title="Unsafe query", evidence="cursor.execute(user_sql)")
    right = finding(title="SQL injection risk", evidence="cursor.execute(user_sql)")
    self.assertEqual(identity(left), identity(right))
```

- [ ] **步骤 2：实现状态协调**

相同 ID 保持 ACTIVE；上次存在但本次验证不存在时转 RESOLVED；已解决 ID 再次出现时转 REOPENED 并增加计数。

- [ ] **步骤 3：实现 SQLite/PostgreSQL 对等存储**

增加 `review_runs` 和 `finding_states`，对 `repository, pull_request, head_sha, mode` 建唯一约束。两种 Store 运行同一 contract 测试。

运行：`python -m unittest tests.test_finding_reconciler tests.test_store_resources -v`

预期：状态转换和数据库对等测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/review/reconciler.py evoagent/store.py evoagent/postgres_store.py tests/test_finding_reconciler.py tests/test_store_resources.py
git commit -m "feat: persist finding lifecycle across reviews"
```

### 任务 7：实现 GitHub inline Review 和评论去重

**文件：**
- 修改：`evoagent/github.py`
- 创建：`evoagent/publication.py`
- 修改：`evoagent/report.py`
- 测试：`tests/test_publication.py`

- [ ] **步骤 1：编写原子 Review payload 测试**

```python
def test_review_payload_contains_line_comments_and_identity(self):
    payload = build_review_payload(report, commit_id="abc")
    self.assertEqual("COMMENT", payload["event"])
    self.assertEqual("src/app.py", payload["comments"][0]["path"])
    self.assertIn("agentic-review:finding:", payload["comments"][0]["body"])
```

- [ ] **步骤 2：扩展 GitHubClient**

新增 `create_review()`、`list_review_comments()` 和 `get_pull_request_commits()`；行号映射失败的 Finding 进入 summary，不发送无锚点 inline comment。

- [ ] **步骤 3：实现双 fingerprint 去重**

分别对规范化 Finding 内容和建议代码计算 fingerprint，跨运行任一命中即视为已发布。

运行：`python -m unittest tests.test_publication tests.test_github -v`

预期：批量发布、回退、去重和错误重试测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/github.py evoagent/publication.py evoagent/report.py tests/test_publication.py
git commit -m "feat: publish deduplicated inline reviews"
```

### 任务 8：增加可靠发布 Outbox

**文件：**
- 修改：`evoagent/store.py`
- 修改：`evoagent/postgres_store.py`
- 修改：`evoagent/task_queue.py`
- 修改：`evoagent/service.py`
- 测试：`tests/test_publication.py`

- [ ] **步骤 1：编写远端失败恢复测试**

```python
def test_outbox_retry_does_not_duplicate_review(self):
    publisher.fail_once()
    service.complete_review(task_id)
    worker.drain()
    self.assertEqual(1, publisher.successful_review_count)
    self.assertEqual("PUBLISHED", store.get_outbox(message_id)["status"])
```

- [ ] **步骤 2：实现 Outbox 状态**

状态为 `PENDING`、`LEASED`、`PUBLISHED`、`FAILED`；payload 带稳定 idempotency key；Review 完成和 Outbox 插入位于同一数据库事务。

- [ ] **步骤 3：接入租约、退避和 DLQ**

复用 `task_queue.py` 的租约语义，发布确认后才 ACK；达到最大尝试次数时保留错误和 payload hash。

运行：`python -m unittest tests.test_publication tests.test_production_features -v`

预期：故障恢复和既有队列测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/store.py evoagent/postgres_store.py evoagent/task_queue.py evoagent/service.py tests/test_publication.py
git commit -m "feat: publish reviews through a durable outbox"
```

### 任务 9：实现 head SHA 增量审查

**文件：**
- 修改：`evoagent/service.py`
- 修改：`evoagent/github.py`
- 创建：`tests/test_incremental_review.py`

- [ ] **步骤 1：编写重复 head 测试**

```python
def test_same_head_sha_reuses_existing_run(self):
    first = service.handle_github_pull_request(payload("abc"), "d1", "h1")
    second = service.handle_github_pull_request(payload("abc"), "d2", "h2")
    self.assertEqual(first["task_id"], second["task_id"])
```

- [ ] **步骤 2：实现增量锚点**

保存最近成功审查的 head SHA；新 head 仅拉取 anchor..head 的提交变化。anchor 不可达或 force-push 时安全回退到完整 PR Diff。

- [ ] **步骤 3：协调状态并更新 summary**

新运行输出 NEW、RESOLVED、REOPENED 数量；失败的增量运行不能错误地解决旧 Finding。

运行：`python -m unittest tests.test_incremental_review tests.test_production_features -v`

预期：重复 head、增量、force-push 和失败保护测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/service.py evoagent/github.py tests/test_incremental_review.py
git commit -m "feat: review pull requests incrementally by head sha"
```

### 任务 10：增加真实 Benchmark Manifest

**文件：**
- 创建：`evoagent/benchmark.py`
- 创建：`tests/test_benchmark_manifest.py`
- 修改：`scripts/run_real_pr_benchmark.py`
- 修改：`README.md`

- [ ] **步骤 1：编写不可变 Manifest 测试**

```python
def test_manifest_fingerprint_changes_with_prompt(self):
    left = manifest(prompt_fingerprint="p1")
    right = manifest(prompt_fingerprint="p2")
    self.assertNotEqual(left.run_fingerprint, right.run_fingerprint)
```

- [ ] **步骤 2：实现数据适配和逐 PR 产物**

适配器只接受固定 revision 的公开数据；输出逐 Finding verdict、聚合指标、错误、Token、成本和耗时，不在 API 中暴露锁定 holdout 内容。

- [ ] **步骤 3：实现 PR 级 bootstrap**

固定随机种子，从 PR 维度重采样，输出 Precision、Recall 和 F1 的 95% 置信区间。

运行：`python -m unittest tests.test_benchmark_manifest tests.test_agentic_evaluation -v`

预期：fingerprint、重放和置信区间测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/benchmark.py scripts/run_real_pr_benchmark.py tests/test_benchmark_manifest.py README.md
git commit -m "feat: publish reproducible real-pr benchmark manifests"
```

### 任务 11：增加资源受限 Docker Sandbox

**文件：**
- 创建：`evoagent/sandbox.py`
- 修改：`evoagent/verifier.py`
- 修改：`evoagent/patching.py`
- 测试：`tests/test_sandbox.py`

- [ ] **步骤 1：编写命令边界测试**

```python
def test_sandbox_disables_network_and_drops_secrets(self):
    command = runner.build_command(worktree, ["python", "-m", "pytest"])
    self.assertIn("--network=none", command)
    self.assertNotIn("EVOAGENT_GITHUB_TOKEN", " ".join(command))
```

- [ ] **步骤 2：实现 SandboxPolicy**

策略固定包含非 root、只读源码、独立写目录、无网络、CPU/内存/PID/超时限制和环境变量 allowlist。Docker 不可用时 deep 修复降级为 Suggestion，不在宿主机执行。

- [ ] **步骤 3：接入 before/after 验证**

同一镜像和命令分别验证原始快照与修复快照；只有 before 证明问题且 after 通过时标记 verified fix。

运行：`python -m unittest tests.test_sandbox tests.test_production_features -v`

预期：边界、降级和前后验证测试通过。

- [ ] **步骤 4：提交**

```bash
git add evoagent/sandbox.py evoagent/verifier.py evoagent/patching.py tests/test_sandbox.py
git commit -m "feat: verify repairs in a restricted sandbox"
```

### 任务 12：发布 GitHub Action、文档和演示

**文件：**
- 创建：`action.yml`
- 创建：`docs/architecture.md`
- 创建：`docs/demo.md`
- 修改：`README.md`
- 修改：`evoagent/cli.py`
- 测试：`tests/test_public_release.py`

- [ ] **步骤 1：增加 Action 合约测试**

```python
def test_action_pins_python_and_exposes_review_mode(self):
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    self.assertIn("mode", action["inputs"])
    self.assertEqual("fast", action["inputs"]["mode"]["default"])
```

- [ ] **步骤 2：实现官方 Action 和 CLI 示例**

Action 只负责安装、调用 CLI、上传 JSON artifact；GitHub 写操作仍由最小权限 token 完成。示例权限明确为 `contents: read`、`pull-requests: write`。

- [ ] **步骤 3：完成面试演示文档**

文档固定覆盖三个场景：重复 delivery 幂等、跨文件 Finding 的证据/反证、修复前后沙箱验证。README 将合成回归指标与真实 Benchmark 分栏展示。

- [ ] **步骤 4：全量验证**

运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q evoagent scripts tests
python -m evoagent.cli doctor
```

预期：全部测试通过、compileall 无输出、doctor 退出码为 0。

- [ ] **步骤 5：提交**

```bash
git add action.yml docs README.md evoagent/cli.py tests/test_public_release.py
git commit -m "docs: publish the review platform demo"
```

## 完成定义

- 所有任务对应的单测、集成测试和 compileall 通过。
- SQLite/PostgreSQL Store contract 一致。
- 新增 GitHub 写操作具备幂等键和失败恢复测试。
- README 不把合成 fixture 指标描述为真实 PR 效果。
- 真实 Benchmark 产物可按 Manifest 重放。
- 每个提交都能解释需求、设计取舍和验证证据。
