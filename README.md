# Agentic Review Harness

面向 GitHub Pull Request 的多智能体代码审查与安全修复系统。

它把一次 PR 审查拆成可追踪的工作流：解析 Diff、分派专长 Agent、收集证据、合并结论，并在满足验证条件时生成安全修复建议。项目同时提供本地规则模式和 OpenAI 兼容模型接入，适合研究 Agent 协作、审查可靠性和反馈驱动的提示词演进。

## 核心能力

- **多 Agent 审查**：Lead 负责规划与综合，Security、Correctness/Reliability 和 Critic 分别负责专项调查与反例挑战。
- **证据约束输出**：Finding 需要绑定文件、行号、规则和证据，降低泛化建议与重复误报。
- **异步任务工作流**：任务状态、执行轨迹、预算、取消和 checkpoint 统一持久化。
- **安全修复闭环**：限定补丁路径，支持 AST/统一 Diff 校验，并要求修复前后测试证据。
- **GitHub 集成**：接收 PR Webhook，可选回写评论、创建独立修复分支。
- **可演进评测**：反馈样本进入 replay/holdout 流程，候选提示词和 Skill 通过门禁后才可激活。

## 评测结果

在 100 个受控 PR Diff 样本上，按仓库划分 Validation / Holdout 评测：

- PR Review 准确率 **92.5%**
- 多 Agent 风险检测 F1 从 81.9% 提升至 **92.5%**
- 高风险召回率从 84.2% 提升至 **94.7%**

以上结果来自项目内生成的合成 fixture（受控样本），不代表真实生产 PR 的表现。评测 harness 与 fixture 位于 `evaluation_data/`，可用 `scripts/` 下的工具离线复现。

## 一次审查如何运行

```text
GitHub PR / REST API
        ↓
解析 Diff，建立风险与上下文
        ↓
Lead 分派任务 → Security / Correctness Worker 调查
        ↓                         ↓
        └──────── Critic 反例挑战 ─┘
                    ↓
          Finding Gate 校验证据与置信度
                    ↓
          Markdown 报告 / 可选安全修复
```

## 架构

```text
HTTP / GitHub Webhook
        │
        ▼
ReviewService ── TaskStore (SQLite / PostgreSQL)
        │
        ▼
AgentRuntime ── checkpoint / budget / trace
        │
        ├── DiffParser + ContextManager
        ├── SkillRegistry + ToolRegistry
        ├── Redis Streams (可选异步队列)
        └── Lead / Workers / Critic
```

## 快速开始

项目使用 Python 3.11；Python 包名 `evoagent` 保留用于兼容现有命令。默认 `local` provider 不需要 LLM 密钥，可以先用规则审查模式启动服务：

```powershell
python -m pip install -e .
python -m evoagent
```

安装后可运行环境诊断；配置有效时退出码为 0，配置缺失或非法时退出码为 1：

```powershell
agentic-review doctor
```

接入 GitHub 前运行 `agentic-review doctor --github`。它分别检查 GitHub App 或 PAT 所需的本地配置、App 私钥文件路径和公开 HTTPS URL，列出缺失的变量名，不打印凭据。GitHub Action 的本地 Diff 审查无需 GitHub 凭据；此命令不会调用 GitHub API，也不证明远端权限已授予。

本地 Diff 可以从 stdin 或 UTF-8 文件审查：

```powershell
git diff | agentic-review review
agentic-review review change.diff
```

自动化场景使用稳定的 JSON 合约：

```powershell
git diff | agentic-review review --format json
```

成功结果包含 `schema_version`、`status`、`reviewer`、`summary`、`files` 和
`findings`；失败结果包含 `schema_version`、`status` 和
`error.code`/`error.message`，同时返回非零退出码。JSON 模式只向 stdout
写入 JSON，默认文本模式保持适合终端阅读的输出。

GitHub Action 调用方应显式声明最小权限：

```yaml
permissions:
  contents: read
  pull-requests: write
```

Action 合约提供 `diff-path`、`mode`、`output-path` 和 `python-version` 输入，
并通过 `report-path` 输出结构化报告路径。当前预览版执行 `fast` 模式；
`deep` 已预留但会明确失败，待分阶段 Pipeline 和沙箱能力完成后开放。
Action 不接收 GitHub token 输入，由调用工作流控制权限。

打开 `http://127.0.0.1:8080/` 查看管理台，健康检查地址为 `http://127.0.0.1:8080/health`。本地开发默认关闭登录；需要启用登录时，在启动前设置 `EVOAGENT_AUTH_REQUIRED=true`、`EVOAGENT_AUTH_SECRET` 和管理员凭据。

服务也可以通过 `POST /v1/reviews` 接收 Diff，通过 `GET /v1/tasks/{id}/report` 获取 Markdown 报告。完整请求模型见 `evoagent/api.py`，README 不展开端点清单。

## 变化规划基础

Python API 可将 Diff 固定到 base/head SHA，筛除 vendor、generated、lock 和二进制文件，确定性地将同名源码与测试配对，并按文件数和估算 Token 上限分组：

```python
from evoagent.review import ChangePlanner, ChangeSet

source = "import math\n\ndef circumference(radius):\n    return math.tau * radius\n"
diff = "--- a/src/app.py\n+++ b/src/app.py\n@@ -3,0 +4 @@\n+    return math.tau * radius\n"
change = ChangeSet.from_diff(diff, "a" * 40, "b" * 40)
groups = ChangePlanner(max_files=2, max_tokens=256).plan(change)
print([(group.group_id, group.paths, group.token_budget) for group in groups])
```

分组按每条新增行 32 Token 估算，单文件超限时标记为 `oversized-file`。可以从 PR head 对应的源码目录为每组构建上下文：

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from evoagent.review import ContextBuilder

with TemporaryDirectory() as checkout:
    app = Path(checkout) / "src/app.py"
    app.parent.mkdir()
    app.write_text(source, encoding="utf-8")
    bundle = ContextBuilder(checkout, change).build(groups[0], token_budget=120)
    print(bundle.total_tokens, [(item.path, item.reason, item.content_hash) for item in bundle.items])
```

每条上下文记录路径、行范围、原文、选择理由、提取方法、估算 Token 和 SHA-256。构建器优先保留变更所在的符号，再补充 import。Python 按静态名称引用优先选取 import。JavaScript 和 TypeScript（含 JSX/TSX）提取静态 import，Go 提取 import 声明。构建器按内容哈希去重，并以分组和调用方指定的较低预算为上限。语法解析失败、扩展名未知或完整符号超预算时，构建器尝试保留预算内的完整变更行。当前可通过 Python API 调用。

## Docker Compose

需要 PostgreSQL、Redis 和 Web 服务时，复制示例配置并填写必需密钥：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写认证密钥、管理员凭据和 AGENTIC_REVIEW_POSTGRES_PASSWORD
docker compose up --build
```

Compose 默认只将 Web 服务绑定到 `127.0.0.1:8080`。

## 模型配置

配置继续兼容 `EVOAGENT_*` 环境变量前缀。默认 `local` provider 使用确定性规则审查，不需要外部模型。需要多 Agent 模式时，选择一个 OpenAI Chat Completions 兼容 provider，并把密钥放在环境变量或本地 `.env` 中：

<details>
<summary>DeepSeek / OpenRouter / 自定义端点</summary>

```powershell
# DeepSeek
$env:EVOAGENT_LLM_PROVIDER = 'deepseek'
$env:EVOAGENT_DEEPSEEK_API_KEY = '<deepseek-api-key>'

# OpenRouter 免费预设
$env:EVOAGENT_LLM_PROVIDER = 'openrouter-deepseek-free'
$env:EVOAGENT_OPENROUTER_API_KEY = '<openrouter-api-key>'

# 其他 OpenAI 兼容端点
$env:EVOAGENT_LLM_PROVIDER = 'custom'
$env:EVOAGENT_LLM_BASE_URL = 'https://example.com/v1'
$env:EVOAGENT_LLM_API_KEY = '<token>'
$env:EVOAGENT_LLM_MODEL = '<model-name>'

python -m evoagent
```

更多参数见 `.env.example`。密钥只通过环境变量读取，不要提交到仓库。
</details>

## GitHub Webhook

推荐使用 GitHub App 接入多个仓库：安装令牌按安装范围签发，服务从 PR Webhook 的 `installation.id` 获取对应令牌。服务接收 `opened`、`reopened` 和 `synchronize` 事件，并异步创建审查任务。当前 Webhook 的 Agent 审查仍要求已配置模型；本地 CLI 的规则审查不受影响。

1. 在 GitHub **Settings → Developer settings → GitHub Apps → New GitHub App** 注册 App。Webhook URL 填 `https://<公网域名>/webhooks/github`，启用 Webhook、设置随机 Secret，并订阅 **Pull request** 事件。仓库权限至少为 `Contents: Read`、`Pull requests: Read`；开启回写评论时将 `Pull requests` 提升为 `Write`。只有启用自动修复并确需创建分支/提交时，才增加 `Contents: Write`。按需要安装到指定仓库。
2. 将生成的私钥文件保存在仓库之外，配置以下环境变量。Webhook Secret 与 GitHub App 私钥、登录密钥分别管理。

```powershell
$env:EVOAGENT_GITHUB_APP_ID = '<app-id>'
$env:EVOAGENT_GITHUB_APP_SLUG = '<app-slug>'
$env:EVOAGENT_GITHUB_PRIVATE_KEY_PATH = '<absolute-path-to-private-key.pem>'
$env:EVOAGENT_GITHUB_WEBHOOK_SECRET = '<webhook-secret>'
$env:EVOAGENT_PUBLIC_BASE_URL = 'https://<公网域名>'
$env:EVOAGENT_AUTO_POST_REVIEW = 'true'
```

3. 启动服务后打开 `/github/install` 进入 GitHub 安装页。App 的 Setup URL 可以填 `https://<公网域名>/github/setup`；当前该回调仅记录 GitHub 传来的 installation ID，不验证该 ID 的所有权，因此不要把回调记录本身当作授权依据。实际 API 调用仍由 GitHub 安装令牌和仓库访问权限控制。

本地单仓库试用也可以继续使用仓库 Webhook 与 fine-grained PAT：

<details>
<summary>配置 Webhook 和 PAT</summary>

```powershell
$webhookBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($webhookBytes)
$env:EVOAGENT_GITHUB_WEBHOOK_SECRET = [Convert]::ToBase64String($webhookBytes)
$env:EVOAGENT_GITHUB_TOKEN = '<GitHub fine-grained PAT>'
$env:EVOAGENT_AUTO_POST_REVIEW = 'true'
```

在仓库 **Settings → Webhooks → Add webhook** 中填写：

- Payload URL：`https://<公网域名>/webhooks/github`
- Content type：`application/json`
- Secret：与 `EVOAGENT_GITHUB_WEBHOOK_SECRET` 相同
- Events：只选择 **Pull requests**

PAT 按需授予最小权限：读取 Diff 使用 `Contents: Read` 和 `Pull requests: Read`；回写评论或创建修复提交时再增加对应的写权限。Webhook Secret 与登录用的 `EVOAGENT_AUTH_SECRET` 是两套不同凭据。
</details>

GitHub 无法访问 `127.0.0.1`，可以使用 Cloudflare Quick Tunnel 或 ngrok：

```powershell
cloudflared tunnel --url http://127.0.0.1:8080
# 或
ngrok http 8080
```

临时转发会同时暴露管理台和 API，因此必须启用认证并使用强密码。自动修复只提交到独立的 `evoagent/fix-pr-*` 分支，不直接修改 PR 源分支。

## 接入方式

最小集成只需要向 `POST /v1/reviews` 提交仓库名、PR 编号、审查模式和 unified diff；任务完成后从 `/v1/tasks/{id}/report` 获取 Markdown 报告。GitHub Webhook 会自动完成这层适配。

`/health` 可用于部署探活，认证开启后其余业务请求使用登录接口返回的 Bearer Token。请求大小、任务步数和超时等边界可以在 `.env.example` 中调整。

## Skills

`skills/` 下的每个目录都是一个可加载的审查协议，包含 `SKILL.md` 和可选的文本资源。Lead 根据任务选择 Skill，Worker 只获得对应的规则和允许使用的工具；这样安全、可靠性等领域规则可以独立演进，而不必把所有内容塞进全局 prompt。

一个 Skill 的最小结构如下：

```text
skills/<skill-name>/
└── SKILL.md
```

`SKILL.md` 的 frontmatter 提供名称、描述和允许使用的工具；正文则定义 Worker 的调查步骤、证据标准和输出约束。

Skill 可以附带文本资源，运行时只把已选中的资源注册给对应 Worker。新增 Skill 时复制一个目录并补充 `SKILL.md` 即可。

## 项目结构

```text
evoagent/          核心服务、Runtime、审查器和存储
skills/            Agent Skill 协议与资源
web/               管理台前端
evaluation_data/   离线评测 fixture
scripts/           服务启动、评测和 fixture 工具
tests/             单元测试与集成测试
```

## 开发

```powershell
python -m unittest discover -s tests -v
python -m compileall -q evoagent scripts tests
```

提交前请确认 `.env`、数据库文件、缓存和本地密钥没有进入 Git；可参考 `.gitignore` 和 `.env.example`。
