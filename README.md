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

项目使用 Python 3.11。默认 `local` provider 不需要 LLM 密钥，可以先用规则审查模式启动服务：

```powershell
python -m pip install -r requirements.txt
python -m evoagent
```

打开 `http://127.0.0.1:8080/` 查看管理台，健康检查地址为 `http://127.0.0.1:8080/health`。本地开发默认关闭登录；需要启用登录时，在启动前设置 `EVOAGENT_AUTH_REQUIRED=true`、`EVOAGENT_AUTH_SECRET` 和管理员凭据。

服务也可以通过 `POST /v1/reviews` 接收 Diff，通过 `GET /v1/tasks/{id}/report` 获取 Markdown 报告。完整请求模型见 `evoagent/api.py`，README 不展开端点清单。

## Docker Compose

需要 PostgreSQL、Redis 和 Web 服务时，复制示例配置并填写必需密钥：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写认证密钥、管理员凭据和 AGENTIC_REVIEW_POSTGRES_PASSWORD
docker compose up --build
```

Compose 默认只将 Web 服务绑定到 `127.0.0.1:8080`。

## 模型配置

默认 `local` provider 使用确定性规则审查，不需要外部模型。需要多 Agent 模式时，选择一个 OpenAI Chat Completions 兼容 provider，并把密钥放在环境变量或本地 `.env` 中：

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

接入方式是 GitHub Webhook + HTTPS 转发 + fine-grained PAT，不需要安装 GitHub App。服务接收 `opened`、`reopened` 和 `synchronize` 事件，并异步创建审查任务。

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
