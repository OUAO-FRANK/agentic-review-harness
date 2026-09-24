# Agentic Review Harness 公开发布设计

## 目标

将现有代码整理为可公开、可运行、可验证的 GitHub 项目，用于投递 AI Agent / 大模型应用开发岗位。项目公开名称为 **Agentic Review Harness**，仓库名为 `agentic-review-harness`。

本次工作只解决公开发布阻塞项，不新增与发布无关的功能，不伪造开发时间或历史提交。

## 项目定位

Agentic Review Harness 是一个面向 GitHub Pull Request 的多 Agent 代码审查系统。公开材料重点展示以下工程能力：

- Lead、Security、Correctness/Reliability 与 Critic 的角色协作；
- 受约束的工具调用、上下文管理、持久化记忆与任务恢复；
- 可动态加载和独立演进的 Agent Skill；
- 离线评测、回归门禁、灰度与回滚机制；
- GitHub Webhook、异步任务、审查报告和可验证自动修复。

README 和简历只描述能够由源码、测试或可复现实验支持的能力。离线合成评测不得表述为真实生产效果。

## 公开范围

本轮包括：

1. 修复现有测试和可重复性问题；
2. 清理敏感配置、数据库、缓存和生成文件；
3. 将公开名称、Python 包、命令、环境变量和 UI 文案统一为 Agentic Review Harness；
4. 加固本地部署默认配置；
5. 重写面向 AI Agent 岗位的 README；
6. 建立诚实、可解释的本地 Git 提交历史；
7. 经用户单独确认后创建 GitHub 仓库并逐次推送。

本轮不包括：

- 为增加提交数量而重写系统；
- 伪造提交时间或虚构原始开发顺序；
- 未经验证的性能优化和生产指标；
- 与公开发布无关的架构重构。

## 已知阻塞项

当前基线共有 75 个单元测试，结果为 43 个错误、1 个失败。

### SQLite 文件句柄

`TaskStore` 使用 `sqlite3.Connection` 的上下文管理执行事务，但该上下文不会关闭连接。Windows 因此无法在测试清理阶段删除临时数据库。

设计：增加统一的连接上下文，在提交或回滚后显式关闭连接，并让现有数据库操作统一使用该入口。不要在测试中通过延迟删除、强制垃圾回收或忽略异常掩盖资源泄漏。

### 评测语料缺失

代码声明读取 `evaluation_data/pr_diff_100.jsonl` 和 `evaluation_data/prompt_evolution_130.jsonl`，但当前目录不包含这些文件。

设计：提供可重复生成的离线 fixture，固定随机种子、样本数量、数据划分和内容指纹。测试不得依赖私人数据、外部网络或未提交文件。公开文档必须区分合成 fixture 与真实 PR 数据。

### SafeFixer 格式断言

AST 修复路径会通过 `ast.unparse()` 输出语义正确的 Python，但测试硬编码要求双引号，导致单引号输出被判定失败。

设计：测试生成代码的 AST 语义、环境变量名和可编译性，不把引号风格作为产品接口契约。

## 重命名策略

重命名在测试基线恢复后进行，避免把既有错误与改名回归混在一起。

需要统一检查：

- GitHub 仓库和 README 标题；
- Python 包、模块导入和启动命令；
- 环境变量前缀；
- Docker 服务名、数据库示例名和分支名前缀；
- Web UI 文案、日志、自动提交和 Draft PR 文案；
- 测试、脚本和内置 Skill 中的产品名称。

除明确记录的兼容入口外，公开代码不保留旧产品名称。若兼容层没有现实调用方，则不添加兼容层。

## 安全与仓库卫生

- `.env`、`*.db`、`__pycache__`、`*.pyc` 和测试缓存不得进入 Git；
- 发布前执行凭据模式扫描，并只报告变量名和文件位置，不输出密钥值；
- Docker Compose 不提供可误用于公网的弱默认密钥或管理员密码；
- `.env.example` 仅保留占位符和安全说明；
- 仓库增加适合公开项目的许可证与必要元数据；
- 不提交本机数据库、运行日志、私有评测数据或个人路径。

## README 结构

README 以中文为主，提供简短英文摘要，首屏直接说明项目用途和 Agent 工程特点。正文至少包含：

1. 项目定位与能力边界；
2. 可核验的核心特性；
3. 系统架构和一次 PR 审查的数据流；
4. 本地快速启动与最小演示；
5. 配置、GitHub Webhook 与安全注意事项；
6. 测试和离线评测方法；
7. 已验证结果及其数据口径；
8. 目录结构、技术取舍和后续计划。

README 不使用未经验证的准确率、吞吐量、用户数或生产级声明。

## Git 历史与发布

采用“干净基线 + 真实改进提交”策略。计划提交如下：

```text
chore: import existing codebase
fix: close sqlite resources after use
test: restore self-contained evaluation fixtures
fix: align safe fixer output contract
refactor: rename project to Agentic Review Harness
security: harden local deployment defaults
docs: rewrite public project documentation
docs: add architecture and verified evaluation results
```

实际提交可根据依赖关系合并或调整，但每个提交必须有单一目的和对应验证。提交日期使用实际日期，不回填虚假时间。

任何 `git commit` 前展示暂存变更摘要；任何 `git push`、公开仓库创建或可见性变更前单独获得用户确认。

## 验证门槛

公开前必须完成：

- 现有测试在 Windows 上通过；
- Python 模块编译检查通过；
- 离线评测 fixture 可从干净环境复现；
- Docker Compose 配置解析通过；
- README 中的快速开始和最小演示可执行；
- 凭据和生成文件扫描无阻塞项；
- 全仓库旧名称扫描只剩已批准的兼容说明；
- Git 暂存内容不包含 `.env`、数据库、缓存或本机文件。

Linux CI 属于公开仓库建立后的验证项；在 CI 通过前，不在简历中声称跨平台测试已完成。

## 简历使用边界

仓库公开且验证通过后再将链接写入简历。可使用“设计并实现”“构建”等表述，但性能、准确率和生产效果只能引用已保存的可复现实验结果。若项目为个人项目，不使用企业生产落地或真实用户规模等无法证明的表述。
