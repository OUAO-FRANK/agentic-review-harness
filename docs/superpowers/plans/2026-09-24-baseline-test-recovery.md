# Agentic Review Harness 基线测试恢复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 安全导入现有代码，修复 SQLite 连接泄漏，恢复可重复的离线评测 fixture，并使现有 75 项测试及 3 项新增回归测试全部通过。

**架构：** 保留现有模块边界。`TaskStore` 统一管理短生命周期 SQLite 连接；独立 fixture 生成模块负责生成并校验公开离线语料；SafeFixer 测试验证 AST 语义而非格式。项目重命名、安全加固和 README 重写留给后续独立计划。

**技术栈：** Python 3.11、标准库 `unittest` / `sqlite3` / `ast` / `json`、Git。

**执行约束：** 当前源代码尚未被 Git 跟踪，无法从现有提交创建包含源码的 worktree，因此本计划在当前工作区执行。每次 `git commit` 前必须展示暂存摘要并获得用户确认；本计划不创建远程仓库，不执行 `git push`。

---

## 文件结构

- 修改：`.gitignore`，补充公开仓库需要排除的本机和测试制品。
- 修改：`evoagent/store.py`，集中管理 SQLite 事务和连接关闭。
- 创建：`tests/test_store_resources.py`，验证每个 SQLite 连接在操作后关闭。
- 创建：`evoagent/evaluation_fixtures.py`，确定性生成公开离线评测语料。
- 创建：`scripts/generate_evaluation_fixtures.py`，提供可重复生成 JSONL 文件的命令入口。
- 创建：`evaluation_data/pr_diff_100.jsonl`，100 条代码审查离线 fixture。
- 创建：`evaluation_data/prompt_evolution_130.jsonl`，130 条提示词演进离线 fixture。
- 修改：`tests/test_evaluation_harness.py`，验证生成器契约和已提交语料一致性。
- 修改：`tests/test_evolution_proof.py`，验证提示词演进 fixture 的划分和漏报口径。
- 修改：`tests/test_advanced.py`，按 AST 语义验证 SafeFixer 输出。

### 任务 1：导入可审计的现有代码基线

**文件：**

- 修改：`.gitignore`
- 暂存：`.dockerignore`、`.env.example`、`.gitignore`、`Dockerfile`、`README.md`、`docker-compose.yml`、`requirements.txt`、`evoagent/`、`scripts/`、`skills/`、`tests/`、`web/`
- 排除：`.env`、`evoagent.db`、`__pycache__/`、`*.pyc`

- [ ] **步骤 1：补全忽略规则**

将 `.gitignore` 调整为：

```gitignore
.env
.env.*
!.env.example
*.db
*.db-shm
*.db-wal
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/
.venv/
venv/
dist/
build/
*.egg-info/
```

- [ ] **步骤 2：验证敏感文件和生成文件被忽略**

运行：

```powershell
git check-ignore -v .env evoagent.db tests/__pycache__/test_service.cpython-312.pyc
```

预期：三个路径都输出匹配的 `.gitignore` 规则；`.env.example` 不应被忽略。

- [ ] **步骤 3：扫描待公开文件中的凭据模式**

运行：

```powershell
rg -l -i --hidden -g '!.git/**' -g '!.env' -g '!*.db' -g '!*.pyc' '(api[_-]?key|access[_-]?token|client[_-]?secret|password|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)' .
```

预期：可以命中配置变量、测试样例和安全规则，但不得发现真实密钥值。只查看变量名和文件位置，不输出 `.env` 内容。

- [ ] **步骤 4：记录导入前测试基线**

运行：

```powershell
python -m unittest discover -s tests -v
```

预期：基线仍为 75 项测试、43 个错误、1 个失败；若数量改变，先解释环境或代码状态差异。

- [ ] **步骤 5：暂存明确列出的项目文件**

运行：

```powershell
git add -- .dockerignore .env.example .gitignore Dockerfile README.md docker-compose.yml requirements.txt evoagent scripts skills tests web
git diff --cached --name-only
```

预期：输出不包含 `.env`、`evoagent.db`、`__pycache__` 或 `*.pyc`。

- [ ] **步骤 6：展示摘要并等待提交许可**

运行：

```powershell
git diff --cached --stat
git diff --cached --check
```

向用户展示文件数、主要目录、基线测试结果和排除项。获得明确许可后才执行：

```powershell
git commit -m "chore: import existing codebase"
```

### 任务 2：关闭所有 SQLite 短生命周期连接

**文件：**

- 创建：`tests/test_store_resources.py`
- 修改：`evoagent/store.py`

- [ ] **步骤 1：编写连接关闭回归测试**

创建 `tests/test_store_resources.py`：

```python
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from evoagent.store import TaskStore


class TaskStoreResourceTests(unittest.TestCase):
    def test_connections_are_closed_after_each_operation(self):
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        real_connect = sqlite3.connect
        opened = []

        def tracked_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection

        try:
            with patch("evoagent.store.sqlite3.connect", side_effect=tracked_connect):
                store = TaskStore(path)
                self.assertIsNone(store.get("missing-task"))

            self.assertGreaterEqual(len(opened), 2)
            for connection in opened:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute("SELECT 1")
        finally:
            for connection in opened:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```powershell
python -m unittest tests.test_store_resources -v
```

预期：FAIL，至少一个被跟踪的连接仍能执行 `SELECT 1`。

- [ ] **步骤 3：实现统一连接上下文**

在 `evoagent/store.py` 中导入 `contextmanager`，保留 `_connect()` 只负责创建连接，新增：

```python
from contextlib import contextmanager
from typing import Iterator

@contextmanager
def _connection(self) -> Iterator[sqlite3.Connection]:
    conn = self._connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()
```

将该文件内所有：

```python
with self._connect() as conn:
```

替换为：

```python
with self._connection() as conn:
```

将所有组合上下文：

```python
with self._lock, self._connect() as conn:
```

替换为：

```python
with self._lock, self._connection() as conn:
```

- [ ] **步骤 4：验证资源测试和受影响测试**

运行：

```powershell
python -m unittest tests.test_store_resources tests.test_harness tests.test_service tests.test_runtime_memory_context tests.test_production_features tests.test_skill_evolution -v
```

预期：不再出现 `PermissionError: [WinError 32]`。除缺失评测语料和 SafeFixer 格式断言外，其余测试通过。

- [ ] **步骤 5：展示摘要并等待提交许可**

运行：

```powershell
git add -- evoagent/store.py tests/test_store_resources.py
git diff --cached --stat
git diff --cached --check
```

获得明确许可后执行：

```powershell
git commit -m "fix: close sqlite resources after use"
```

### 任务 3：恢复可重复的离线评测 fixture

**文件：**

- 创建：`evoagent/evaluation_fixtures.py`
- 创建：`scripts/generate_evaluation_fixtures.py`
- 创建：`evaluation_data/pr_diff_100.jsonl`
- 创建：`evaluation_data/prompt_evolution_130.jsonl`
- 修改：`tests/test_evaluation_harness.py`
- 修改：`tests/test_evolution_proof.py`

- [ ] **步骤 1：先写生成契约测试**

在 `tests/test_evaluation_harness.py` 增加：

```python
from evoagent.evaluation_fixtures import (
    generate_controlled_cases,
    generate_prompt_evolution_cases,
)

def test_generated_fixtures_match_checked_in_corpora(self):
    controlled = generate_controlled_cases()
    prompt = generate_prompt_evolution_cases()
    self.assertEqual(100, len(controlled))
    self.assertEqual(130, len(prompt))
    self.assertEqual(controlled, load_controlled_pr_cases())
    self.assertEqual(prompt, load_prompt_evolution_cases())
```

补充对应 import：

```python
from evoagent.evolution_proof import load_prompt_evolution_cases
```

在 `tests/test_evolution_proof.py` 增加：

```python
def test_prompt_fixture_has_reproducible_feedback_distribution(self):
    cases = generate_prompt_evolution_cases()
    validation_findings = sum(
        len(case["expected_findings"])
        for case in cases if case["split"] == "validation"
    )
    holdout_findings = sum(
        len(case["expected_findings"])
        for case in cases if case["split"] == "holdout"
    )
    self.assertEqual(32, validation_findings)
    self.assertEqual(8, holdout_findings)
```

- [ ] **步骤 2：运行测试并确认缺少生成模块**

运行：

```powershell
python -m unittest tests.test_evaluation_harness tests.test_evolution_proof -v
```

预期：ERROR，`evoagent.evaluation_fixtures` 不存在，且现有 JSONL 文件仍缺失。

- [ ] **步骤 3：实现确定性 fixture 生成器**

创建 `evoagent/evaluation_fixtures.py`。实现以下稳定接口：

```python
def generate_controlled_cases() -> list[dict]:
    """Return 100 cases: 10 repositories, 40 risk and 60 clean cases."""

def generate_prompt_evolution_cases() -> list[dict]:
    """Return 130 cases: 8 validation and 2 holdout repositories."""

def write_fixture_files(output_dir: str) -> dict[str, str]:
    """Write both corpora as sorted UTF-8 JSONL and return their paths."""
```

生成器必须使用固定模板而不是随机数：

```python
CONTEXT_SCENARIOS = (
    ("SEC-PATH-TRAVERSAL", "high", "value = open(base / user_path)"),
    ("SEC-YAML-LOAD", "high", "value = yaml.load(payload)"),
    ("SEC-WEAK-HASH", "medium", "value = hashlib.md5(payload).hexdigest()"),
    ("SEC-INSECURE-TEMPFILE", "medium", "path = tempfile.mktemp()"),
    ("SEC-WEAK-RANDOM", "medium", "token = random.random()"),
    ("REL-UNBOUNDED-RETRY", "medium", "while True:"),
    ("SEC-ASSERT-AUTH", "medium", "assert user.is_admin"),
    ("SEC-INSECURE-COOKIE", "medium", "response.set_cookie('sid', value, secure=False)"),
)
```

每条 case 必须包含 `schema_version`、`id`、`repository`、`pull_request`、`split`、`source`、`diff`、`expected_findings`、`after_files` 和 `repair_validation`。`source.kind` 固定为 `offline-fixture`。路径固定为 `app.py`，新增行号固定为 1。

`generate_controlled_cases()` 为每个仓库生成 10 条 case，其中 4 条风险 case、6 条干净 case；前 8 个仓库标记 `validation`，后 2 个标记 `holdout`。

`generate_prompt_evolution_cases()` 为每个仓库生成 13 条 case。前 8 个仓库标记 `validation`，每个仓库 4 条 ContextRule 风险 case；后 2 个仓库标记 `holdout`，每个仓库 4 条相同规则族风险 case；其余为干净 case。这样 baseline 的 32 个 validation 漏报可以产生学习反馈，candidate 在 holdout 上也能获得可验证提升。

- [ ] **步骤 4：添加生成命令并写出 JSONL**

创建 `scripts/generate_evaluation_fixtures.py`：解析可选 `--output-dir`，默认写入仓库根目录的 `evaluation_data/`，调用 `write_fixture_files()`，打印两个路径和 case 数量，不输出数据内容。

运行：

```powershell
python scripts/generate_evaluation_fixtures.py
```

预期：创建两个 JSONL 文件，分别为 100 行和 130 行。

- [ ] **步骤 5：验证 fixture 契约和演进证明**

运行：

```powershell
python -m unittest tests.test_evaluation_harness tests.test_evaluation_experiments tests.test_evolution_proof -v
```

预期：全部 PASS；若候选没有在 validation 和 holdout 上提升，只调整公开 fixture 的场景分布，不放宽演进门禁。

- [ ] **步骤 6：验证重复生成无差异**

运行：

```powershell
python scripts/generate_evaluation_fixtures.py
git diff -- evaluation_data
```

预期：第二次生成后 `evaluation_data/` 无差异。

- [ ] **步骤 7：展示摘要并等待提交许可**

运行：

```powershell
git add -- evoagent/evaluation_fixtures.py scripts/generate_evaluation_fixtures.py evaluation_data tests/test_evaluation_harness.py tests/test_evolution_proof.py
git diff --cached --stat
git diff --cached --check
```

获得明确许可后执行：

```powershell
git commit -m "test: restore self-contained evaluation fixtures"
```

### 任务 4：按 Python 语义验证 SafeFixer 输出

**文件：**

- 修改：`tests/test_advanced.py`

- [ ] **步骤 1：把引号格式断言替换为 AST 契约**

在 `tests/test_advanced.py` 顶部导入 `ast`，将：

```python
self.assertIn('password = os.environ["PASSWORD"]', result["content"])
```

替换为：

```python
tree = ast.parse(result["content"])
assignment = next(
    node for node in tree.body
    if isinstance(node, ast.Assign)
)
self.assertEqual("password", assignment.targets[0].id)
self.assertIsInstance(assignment.value, ast.Subscript)
self.assertEqual("PASSWORD", assignment.value.slice.value)
self.assertTrue(any(
    isinstance(node, ast.Import)
    and any(alias.name == "os" for alias in node.names)
    for node in tree.body
))
```

保留对不受支持规则不被修改的原有断言。

- [ ] **步骤 2：验证目标测试**

运行：

```powershell
python -m unittest tests.test_advanced.AdvancedFeatureTests.test_safe_fixer_changes_only_supported_rules -v
```

预期：PASS，且 `evoagent/fixer.py` 无需修改。

- [ ] **步骤 3：展示摘要并等待提交许可**

运行：

```powershell
git add -- tests/test_advanced.py
git diff --cached --stat
git diff --cached --check
```

获得明确许可后执行：

```powershell
git commit -m "test: assert safe fixer semantics"
```

### 任务 5：验证稳定基线并记录后续输入

**文件：**

- 不创建业务文件；只更新本计划中的复选框和实际验证结果。

- [ ] **步骤 1：运行完整测试**

运行：

```powershell
python -m unittest discover -s tests -v
```

预期：78 项测试全部通过。新增三项测试后数量从 75 增至 78；如实际新增数量不同，以测试发现输出为准并说明原因。

- [ ] **步骤 2：运行 Python 编译检查**

运行：

```powershell
python -m compileall -q evoagent scripts tests
```

预期：退出码 0。

- [ ] **步骤 3：确认工作区和历史边界**

运行：

```powershell
git status --short
git log --oneline --decorate
git ls-files | rg '(^|/)(\.env|.*\.db|__pycache__|.*\.pyc)$'
```

预期：不输出敏感或生成文件；工作区只包含明确说明的计划进度变更。

- [ ] **步骤 4：形成阶段报告**

向用户报告：测试总数、通过数、fixture 数量和指纹、未进入 Git 的本机文件、实际提交列表，以及下一阶段“项目重命名与部署安全加固”的输入。计划复选框更新在提交前仍需展示摘要并获得许可。
