# BoetClaw - DeepAgents 钻井智能体系统

BoetClaw 是基于 LangChain DeepAgents / LangGraph / FastAPI / React 构建的本地优先钻井智能体工作台，提供对话、规划、工具、技能、多 Agent、渠道、调度、领域数据和运行追踪能力。

## 当前项目状态

当前版本可定位为“后端功能面较完整、具有首版 React 管理控制台的单机 MVP”，不应表述为全部业务闭环完成或生产就绪。

- 后端最近一次本地验证全量 pytest `213`（`--collect-only`）；前端 Vitest `29`、E2E `8`（fake，沿用）、coverage/build 与 Compose 配置校验通过。
- 默认使用每 Agent 独立 SQLite checkpoint，支持单机 Agent/进程重建后的恢复校验；`memory` 仅为显式降级。
- 工具审批单实例幂等裁决、完整多 Agent 计划 API/隔离、同步/SSE 统一及单进程执行级取消已完成。
- task、`/stop` 与流停止统一使用进程内运行注册表；不支持跨进程、多副本或重启后的活动运行取消。
- 井/井段/日报/参数/LAS 单实例领域 CRUD 已闭环；不承诺数据库事务或多实例一致性。
- Cron history / Heartbeat 持久、渠道路由验签、插件扫描删除、Agent 磁盘发现与 purge、idle 逐出、会话删除/归档、产物删除与 SHA256、LAS 上传门禁已完成。
- 前端组件测试、Playwright Chromium E2E（fake Provider）与 `.github/workflows/ci.yml` 已建立；本地可用 `scripts/ci-local.ps1` / `ci-local.sh`。Git 仓库已初始化；推送到 GitHub（目标 `NO1117/boetclaw`）后需启用 Actions / required checks。真实 Provider/渠道仍非默认门禁。
- PLAN-100—710 已完成（含 PLAN-500 文档治理与 PLAN-650 运维验收同步、PLAN-670—710 会话/产物/LAS 治理）。RBAC、多实例、真实 Provider/渠道默认门禁等仍未排期。

详见 [`docs/PROJECT_STATUS_REPORT.md`](docs/PROJECT_STATUS_REPORT.md) 和 [`docs/ACCEPTANCE_CHECKLIST.md`](docs/ACCEPTANCE_CHECKLIST.md)。

事实判定顺序为：当前代码与配置、实际测试结果、运行实例 OpenAPI、现行文档、历史计划/进度。API 请求字段、校验和状态码以运行实例的 `/docs` 与 `/openapi.json` 为契约真源。

## 核心能力

| 模块 | 当前状态 | 能力与边界 |
|---|---|---|
| 智能体核心 | 部分闭环 | DeepAgents、子智能体、PlanGate 和单机 SQLite checkpoint 已接入；不支持多实例恢复 |
| 规划与审批 | 单实例闭环 | 完整 ExecutionRef、工具审批及多 Agent 计划的 SQLite/API 重建恢复已验证；不保证跨资源 exactly-once |
| 安全执行 | 部分闭环 | ToolGuard、路径/Shell 规则和审批历史已实现；不是 OS 沙箱 |
| 技能与插件 | 已有主体 | 技能池、工作区副本、扫描、插件安装扫描/删除和 MCP 管理可用；非 OS 沙箱 |
| 多智能体 | 单实例闭环 | Workspace 文件/技能/checkpoint、同步/SSE、计划恢复、磁盘列表发现、tombstone/purge 与 idle 定时逐出已闭环 |
| 模型 Provider | 已有主体 | OpenAI、Anthropic、Ollama 配置、模型和检测可用 |
| 渠道与调度 | 部分闭环 | Cron history/Heartbeat 持久与渠道路由验签已闭环；真实回发联调仍未排期 |
| 钻井领域 | 单实例闭环 | 井、井段、日报、参数、LAS 单实例 CRUD 与关系保护已闭环；不承诺数据库事务或多实例一致性 |
| 前端控制台 | 首版可用 | React 路由与管理页面可构建；Vitest 与 Playwright E2E（fake）已覆盖关键路径 |
| 可观测性 | 已有主体 | Trace/Run、JSONL、timeline、Prometheus 和可选 OTel 已接入 |

## 架构概览

```text
React Console
  ├─ Chat / PlanConfirm / ApprovalCard
  ├─ Skills / Providers / Cron / Plugins
  └─ Trace Timeline
        │
FastAPI REST + SSE
        │
BoetClaw Agent Factory
  ├─ ObservabilityMiddleware
  ├─ PlanGateMiddleware
  ├─ ToolGuardMiddleware
  ├─ SummarizationMiddleware (optional)
  ├─ Skills / Plugins / MCP tools
  └─ FilesystemBackend / Memory / Store
        │
DeepAgents + LangGraph
```

更多细节见 `docs/ARCHITECTURE.md`。

## 快速开始

后端建议使用 Python 3.11-3.13。Python 3.14 目前会触发 LangChain/Pydantic 兼容性问题。

### 一键安装

Windows：

```powershell
.\scripts\install.ps1
```

Linux/macOS：

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

安装完成后编辑 `backend/.env`，至少配置一种模型提供商。

### 启动后端

```bash
cd backend
# Windows
.\.venv\Scripts\python.exe run.py

# Linux/macOS
.venv/bin/python run.py
```

API 文档：http://localhost:8000/docs

### 启动前端

```bash
cd frontend
npm run dev
```

前端：http://localhost:5173

## Docker Compose

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

访问：

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000/docs
- 后端内置前端：http://localhost:8000/ui/

启用可选 Ollama：

```bash
docker compose --profile ollama up --build
```

并在 `backend/.env` 中设置：

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5
OLLAMA_BASE_URL=http://ollama:11434
```

接入 OpenAI-compatible 本地模型服务（如 vLLM、LM Studio、LocalAI、Ollama `/v1` 兼容接口）：

```env
LLM_PROVIDER=openai
LLM_MODEL=qwen3.6-35b-a3b
OPENAI_API_KEY=not-needed
OPENAI_BASE_URL=http://localhost:8001/v1
```

## 关键配置

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=
OPENAI_BASE_URL=

TOOL_GUARD_ENABLED=true
TOOL_GUARD_LEVEL=smart

MEMORY_BACKEND=file
CONTEXT_SUMMARIZATION_ENABLED=false

CHECKPOINT_BACKEND=sqlite
CHECKPOINT_SQLITE_PATH=./workspace/checkpoints

ENABLED_PLUGINS=

OTEL_ENABLED=true
TRACE_PERSIST_ENABLED=true

# 控制台经保险箱保存 Provider API Key 时需要（32 字节随机 Base64；勿提交真实值）
BOETCLAW_MASTER_KEY=
```

完整配置见 `backend/.env.example`；保险箱与主密钥说明见 `docs/SECURITY.md`。

## 常用 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/agent/chat` | 同步对话 |
| `POST` | `/api/v1/agent/chat/stream` | SSE 流式对话 |
| `POST` | `/api/v1/agent/plan/confirm` | 计划确认 |
| `GET` | `/api/v1/security/approvals` | 待审批工具调用 |
| `GET` | `/api/v1/skills` | 技能池与工作区技能 |
| `GET` | `/api/v1/agents` | 多智能体工作区 |
| `GET` | `/api/v1/providers` | 模型 Provider |
| `GET` | `/api/v1/tasks/cron` | Cron 任务 |
| `GET` | `/api/v1/plugins` | 插件列表 |
| `GET` | `/api/v1/monitor/trace/{trace_id}/timeline` | 结构化时间线 |

完整索引见 `docs/API.md`。

## 渠道接入

支持：

- 钉钉：`/api/v1/gateway/dingtalk/webhook`
- 飞书：`/api/v1/gateway/feishu/webhook`
- QQ / OneBot / NapCat：`/api/v1/gateway/qq/webhook`
- Telegram：`/api/v1/gateway/telegram/webhook`

详见 `docs/CHANNELS.md`。

## 项目结构

```text
boetclaw/
├── backend/
│   ├── app/
│   │   ├── agents/          # 多智能体 workspace
│   │   ├── api/routes/      # REST API
│   │   ├── core/            # 配置、工厂、可观测性、OTel
│   │   ├── middleware/      # PlanGate / ToolGuard / Observability
│   │   ├── providers/       # OpenAI / Anthropic / Ollama
│   │   ├── security/        # ToolGuard
│   │   ├── services/        # Gateway / Cron / Heartbeat
│   │   ├── skills_system/   # 技能池
│   │   └── plugins/         # 插件加载
│   ├── skills/              # 内置技能
│   ├── plugins_ext/         # 外部插件（默认不启用）
│   ├── openapi.snapshot.json
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/                # React 控制台
├── docs/                    # 架构/API/渠道/安全/部署文档
├── scripts/                 # 安装与本地 CI 脚本
├── .github/workflows/ci.yml # push/PR 门禁
├── Dockerfile
└── docker-compose.yml
```

## 文档

文档总入口：[`docs/README.md`](docs/README.md)。

- [`docs/PROJECT_STATUS_REPORT.md`](docs/PROJECT_STATUS_REPORT.md)：当前完成度、验证结果和主要风险
- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)：`REQ-*` 需求、范围和验收原则
- [`docs/FEATURE_CATALOG.md`](docs/FEATURE_CATALOG.md)：`FUN-*` 功能、实现路径和缺口
- [`docs/ACCEPTANCE_CHECKLIST.md`](docs/ACCEPTANCE_CHECKLIST.md)：REQ—FUN—API—PAGE—TEST—PLAN 验收映射
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)：只保留当前有效的 `PLAN-*` 落地计划
- [`docs/PROGRESS.md`](docs/PROGRESS.md)：落实清单与本轮实现记录
- [`docs/DOCUMENT_INVENTORY.md`](docs/DOCUMENT_INVENTORY.md)：材料台账、归档与事实来源
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：当前系统架构与运行边界
- [`docs/API.md`](docs/API.md)：REST API 人工索引；精确契约以运行时 OpenAPI 为准
- [`docs/TESTING.md`](docs/TESTING.md)：测试矩阵、命令、结果和缺口
- [`docs/SECURITY.md`](docs/SECURITY.md)：安全控制与已知风险
- [`docs/CHANNELS.md`](docs/CHANNELS.md)：渠道接入、队列、回发与 stub 边界
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)：本地与容器部署、持久化和生产前置

2026-07-15 前的原始长计划、进度和专题快照保存在 `docs/archive/2026-07-15/`，仅用于追溯。

## 验证

本地一键复现主 CI 门禁：

```powershell
.\scripts\ci-local.ps1
```

```bash
./scripts/ci-local.sh
```

或分项：

```bash
cd backend && PYTHONPATH=. python -m pytest -q
cd frontend && npm test -- --run && npm run test:coverage && npm run build && npm run test:e2e
docker compose config --quiet
```

GitHub Actions：见 `.github/workflows/ci.yml`；required checks 启用步骤见 `docs/DEPLOYMENT.md`。

## 首版发布

- 发布说明：[`docs/RELEASE.md`](docs/RELEASE.md)
- 安全策略：[`SECURITY.md`](SECURITY.md)（技术细节见 [`docs/SECURITY.md`](docs/SECURITY.md)）

## License

[MIT](LICENSE)
