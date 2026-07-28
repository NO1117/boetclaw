# BoetClaw 架构说明

> 基线：2026-07-17。本文描述当前代码的真实运行结构；目标设计或历史阶段完成标记不作为实现事实。
> 最近验证（2026-07-20）：后端 pytest `213 passed`；Vitest `5 files / 29 passed`；E2E `8 passed`（fake Provider）；ruff/mypy/OpenAPI/coverage/build/compose 均通过。PLAN-600—710 运维闭环已完成。该架构仍不支持领域跨进程事务、多实例协调或数据库迁移。

## 1. 系统概览

BoetClaw 是单实例、本地文件持久化优先的钻井智能体工作台。React 控制台通过 `/api/v1` 调用 FastAPI；FastAPI 编排 DeepAgents/LangGraph、工具/技能/插件/MCP、任务与渠道服务；运行数据主要写入 `backend/workspace`。

```text
Browser / Channel Webhook / API Client
            │ HTTP / SSE
            ▼
FastAPI app.main
  ├─ CORS
  ├─ ApiSecurityMiddleware（可选 Token/JWT + 内存限流）
  ├─ /api/v1/* routers
  └─ /ui（存在 frontend_dist 时）
            │
            ├──────── Tasks / Cron / Heartbeat / Gateway
            │
            ▼
AgentManager（default）或 MultiAgentManager（非 default）
            │
BoetClawAgentFactory
  ├─ DeepAgents + LangGraph
  ├─ built-in + MCP + enabled plugin tools
  ├─ default subagents
  ├─ skills / memory / backend / checkpointer
  └─ middleware stack
            │
            ▼
LLM Provider / MCP / local filesystem / channel APIs
```

## 2. 代码分层

| 层 | 职责 | 主要路径 |
|---|---|---|
| Web 控制台 | 对话、任务、Agent、Trace、领域数据、产物和设置页面 | `frontend/src/App.tsx`、`frontend/src/components/`、`frontend/src/services/api.ts` |
| API | REST/SSE 路由、Pydantic 入参与响应 | `backend/app/api/routes/`、`backend/app/api/schemas.py` |
| 应用编排 | 生命周期、Agent 构建、运行上下文、Trace | `backend/app/main.py`、`backend/app/core/` |
| Agent 运行时 | 默认 Agent、多 Workspace、状态和调用适配 | `backend/app/agents/`、`backend/app/core/agent.py` |
| 横切中间件 | 可观测、计划门控、工具安全、API 安全 | `backend/app/middleware/` |
| 扩展系统 | 工具、MCP、技能、插件、命令、Provider | `backend/app/tools/`、`skills_system/`、`plugins/`、`commands/`、`providers/` |
| 业务服务 | 任务、Cron、Heartbeat、消息渠道 | `backend/app/services/` |
| 钻井领域 | 井、井段、日报、参数、LAS | `backend/app/domain/` |
| 安全 | Guardian、策略引擎、审批、Console JWT | `backend/app/security/` |
| 团队身份 | 用户/会话/RBAC/资源 ACL/审计（单工作区） | `backend/app/identity/`；`api/routes/auth.py`、`users.py` |

## 3. 启动与关闭流程

### 3.1 应用构造

`app.main` 创建 FastAPI，依次注册 CORS 与 `ApiSecurityMiddleware`，再把所有业务 Router 统一挂到 `/api/v1`。OpenTelemetry 在模块加载时调用 `setup_otel(app)`；若存在 `frontend_dist`，额外挂载 `/ui` 静态站点。

### 3.2 两阶段启动

1. FastAPI lifespan 调用 `phase1_fast`：
   - 创建 `workspace_dir`。
   - 初始化统一 `CheckpointProvider`；SQLite 初始化失败时 health 降级且 Agent 不就绪。
   - 从设置注册渠道并启动内存队列消费者。
   - 扫描插件目录；只有 `ENABLED_PLUGINS` 中的插件工具进入运行时。
   - 设置 `app.state.ready=true`、`agent_ready=false`。
2. lifespan 创建后台任务执行 `phase2_background`，不阻塞 HTTP 服务启动：
   - 连接 MCP。
   - 构建默认 Agent。
   - 成功后设置 `agent_ready=true`。
   - 启动 APScheduler Cron 和 Heartbeat。
3. Phase 2 失败会记录日志并保持 `agent_ready=false`，不会终止 FastAPI 进程。

`GET /api/v1/monitor/health` 同时观察应用与 Agent 就绪状态，并绕过 API 鉴权及限流，供容器探活。

### 3.3 关闭

lifespan 退出时取消并等待 Phase 2 任务，通过单进程 `RunRegistry` 取消并等待已登记的任务、同步/SSE 与渠道 Agent 子任务，再关闭 Cron、停止渠道消费者、断开 MCP，并关闭 `CheckpointProvider` 管理的 SQLite 连接。未登记的第三方后台工作不在该协调范围内。

## 4. Agent 构建与运行

### 4.1 默认 Agent

`AgentManager` 在 Phase 2 构建单个默认 Agent：

- 通过 `CheckpointProvider` 获取默认 Agent 专属 checkpointer；
- 全局 `AGENTS.md` 作为文件记忆（存在时）；
- `backend/skills` 作为默认技能目录；
- 工具由 Agent Factory 统一组装；
- 同步与流式调用分别使用 `ainvoke` 和 `astream`。

### 4.2 非默认 Workspace Agent

`MultiAgentManager` 按 `agent_id` 懒加载：

- 根目录：`workspace/agents/{agent_id}`；
- 文件后端：该目录下的 `files/`，由 `FilesystemBackend` 隔离；
- 技能：工作区 `skills/` 与启停状态；
- checkpoint：每个 Workspace 使用 provider 管理的 Agent 专属 saver；
- 可选 Store：`memory_backend=store` 时使用进程内 `InMemoryStore`；
- 每 Agent 一把 `asyncio.Lock`，避免并发重复构建。

同步 `/agent/chat` 与 SSE `/agent/chat/stream` 均通过共享 `prepare_chat()` 和严格 resolver 路由到 default 或已注册 Workspace Agent；计划/审批 resume 使用相同解析规则，未知或已删除 Agent 不会静默创建或回退 default。

`list_agents` / `GET /agents` 会扫描 `agents_root` 子目录（跳过 `.deleted` tombstone），保证 default 始终在册，并仅懒加载元数据而不强制 build graph。默认删除写 tombstone 并保留目录与 checkpoint（`checkpoint_retained=true`）；`purge=true` 时删除工作区目录，经 `CheckpointProvider.purge` 清理该 Agent checkpoint，并留下 `.purged/{id}` 标记。tombstone/purge 后列表不可见，resume 返回 409；default 不可删除/不可 purge。`evict_idle()` 已实现但没有看到生命周期定时调用。

### 4.2.1 附件子系统（PLAN-800）

```text
前端上传 → POST /agents/{id}/attachments
  → AttachmentService（签名校验、Agent 隔离目录、SHA-256）
  → 进程内后台解析（pypdf / python-docx / openpyxl / python-pptx / 文本）
  → 结构分块 + 本地关键词索引
聊天发送 attachment_ids → prepare_chat → resolve_attachment_ids_for_chat
  → 关键词检索相关块 → 注入 LangChain user content
  → session 仅存 ID/摘要；Trace 记录块引用与截断
```

- 存储：`workspace/attachments/{agent_id}/{attachment_id}/`（`original.bin`、`meta.json`、`chunks.json`、`keyword_index.json`）。
- 生命周期：`uploading/uploaded/parsing/ready/failed/expired/deleted`；删除写 tombstone；清理任务跳过仍被会话 `attachment_refs` 引用的附件。
- 兼容：旧版 `ChatRequest.attachments[]` Base64 路径仍可用；默认前端走两阶段 `attachment_ids`。

### 4.3 模型、工具与子智能体

Agent Factory 解析 `provider:model`：

- Provider 已配置时，通过 `ProviderManager` 创建模型；
- 未配置或解析失败时，回退为 DeepAgents 可延迟解析的字符串。

工具集合为：

```text
builtin tools + MCP tools + enabled plugin tools
```

默认子智能体为 `researcher`、`coder`、`chart-analyst`、`reviewer`，不同子智能体使用受限工具子集。其配置目前是代码内固定配置。

## 5. Agent 中间件栈

实际顺序由 `BoetClawAgentFactory` 固定为：

```text
Observability → PlanGate → ToolGuard → Summarization（可选）→ extra middleware
```

### 5.1 ObservabilityMiddleware

- `before_model` 记录 THINKING。
- `after_model` 记录模型计划的工具调用。
- `wrap_tool_call` 在工具调用前后记录 TOOL_CALL/TOOL_RESULT。
- Trace/Run ID 由 ContextVar 贯穿 Agent、工具和产物元数据。

### 5.2 PlanGateMiddleware

- `/plan` 前缀由 `AgentManager.invoke()` 剥离并设置 `plan_phase=planning`。
- planning 状态只允许 `write_todos`，其他工具返回错误 ToolMessage。
- `write_todos` 执行后调用 LangGraph `interrupt()`，前端通过 confirm API 用 `Command(resume=...)` 恢复。
- invoke 解析真实 Interrupt 并生成不可变 `ExecutionRef`；approve/reject/edit 由独立计划恢复服务处理。服务先以精确 ref 校验 pending 历史，再恢复原图并写成功/失败审计；历史可按 Agent+thread 查询。

### 5.3 ToolGuardMiddleware

- 调用 `ToolGuardEngine`，合并规则、文件路径和 Shell Guardian 结果。
- 拒绝时直接返回安全错误 ToolMessage。
- 需审批时按 `agent_id + thread_id + tool_call_id` 幂等创建或复用审批，再触发 `interrupt()`。
- 批准后调用原工具，拒绝后停止该次工具执行。
- `strict/smart/auto/off` 由运行时设置控制。

LangGraph resume 会从节点开头重放；稳定审批 key 保证重放复用同一记录。ToolGuard 不再捕获中断异常后默认批准。图外直接调用或中断失败会抛出错误，受保护 handler 不执行；正常 LangGraph 上下文则由图捕获中断并返回服务端生成的 ref。

### 5.4 SummarizationMiddleware

由 `CONTEXT_SUMMARIZATION_ENABLED` 控制，默认关闭。构建失败时记录告警并禁用，不阻止 Agent 创建。

## 6. 前后端数据流

### 6.1 同步对话

```text
ChatPanel → POST /api/v1/agent/chat
  → 解析 body lang / Accept-Language
  → slash command 预处理
  → default AgentManager 或非默认 Workspace Agent
  → DeepAgents 模型/工具循环
  → 计划或工具审批时 interrupt
  → 记录 session + trace/run
  → ChatResponse
```

### 6.2 流式对话

```text
前端 → POST /api/v1/agent/chat/stream
  → prepare_chat（命令/语言/source/thread/Agent/trace/run）
  → 对目标 graph 执行 stream_agent.astream(messages, updates, subgraphs)
  → SSE v1 event:update
  → 中断：注册 ExecutionRef + 写会话 + event:interrupt
  → 成功：写会话
  → event:done（一次）
  ↘ 命令：event:command + done；异常：event:error
```

SSE 是 POST 响应流，不是浏览器原生 `EventSource` GET。v1 data envelope 带 `event/data/version/thread_id/agent_id/trace_id/run_id`；前端以纯函数按完整 block 解析多行 data、CRLF 和分块边界，并兼容旧 SSE 结构。

### 6.3 计划与审批恢复

```text
write_todos / 高风险工具
  → LangGraph Interrupt(id, payload)
  → 生成 ExecutionRef(agent/thread/namespace/interrupt/type)
  → 对话响应返回 execution_ref + payload / 审批记录绑定相同 ref
  → 用户 approve|reject|edit
  → 独立 PlanResumeService 或 ApprovalResumeService
  → 校验 approval/ref/type/pending/decision
  → 原子 pending→resuming → 共享 GraphResumeAdapter
  → Command(resume=...) 成功后写 approved/rejected
  ↘ 失败写不可自动重试的 resume_failed
  → 原 thread checkpoint 恢复
```

默认 checkpoint 使用 `langgraph-checkpoint-sqlite==3.1.0` 的 `AsyncSqliteSaver`。每个 Agent 对应独立数据库，因而相同 thread ID 不会跨 Agent 串线；`memory` 仅为显式降级且 health 标明不支持跨重启。
底层 adapter 保留进程内 ref→graph 注册表作为快速路径；非默认 Agent 即使命中注册表也先经统一 resolver 校验未删除。注册表缺失时按 `ExecutionRef.agent_id` 重建默认/Workspace graph，从 SQLite 检查真实 interrupt ID 后再恢复，并恢复相同 Agent/thread 的运行上下文。checkpoint、pending 历史或原 Agent 不匹配时返回明确 4xx。计划旧 thread-only 兼容仅匹配唯一 default pending；审批旧缺 ref 记录仍不可恢复。

该布局只面向单实例：每 Agent 独立 DB 是 Agent 隔离手段，不是多实例协调方案。审批 JSON、LangGraph SQLite 与工具写入的外部资源没有共同事务；进程在工具副作用完成后、graph/审批状态写回前崩溃时无法判定副作用结果。因此这里的“单次执行”是受测正常流程与单进程并发语义，不是跨资源或分布式 exactly-once。

### 6.4 后台任务（持久化队列）

任务状态持久化在 SQLite WAL（`workspace/tasks/task_queue.sqlite3`），启动时幂等迁移旧 `task_history.json`。单实例 Worker 通过租约领取 `queued/scheduled/retry_wait` 任务；事务条件更新防止并发竞态。重启后未完成的 `running/leased/cancelling` 标记为 `interrupted`，不伪装继续运行。

API `/run` 与渠道仍可通过 `RunRegistry` 直接触发协程（兼容路径）；Worker 路径使用冻结 Agent/连接快照。状态含 `queued/scheduled/leased/running/retry_wait/dead_letter/interrupted` 等；旧 `pending` 映射为 `queued`。

### 6.5 渠道消息

```text
Webhook → 渠道解析
  → 白名单 → 用户限流
  → ChannelManager 有界队列
  → 创建 task → default Agent
  → 渠道 renderer/send_reply
  → task + message history + trace
```

队列入队失败时路由会回退到 BackgroundTasks。渠道消息历史落盘，但为了可序列化会剔除原消息对象，所以重启恢复的旧失败记录不可重试。

### 6.6 Cron 与 Heartbeat

APScheduler 使用 UTC 时区。Cron Job 写入 `.cache/cron_jobs.json`，触发时按 `agent_id` 选择 Agent，可选回发渠道；运行历史写入 `.cache/cron_history.json`（上限 500）。Heartbeat 复用同一 scheduler；PUT 写入 `.env` 的 `HEARTBEAT_*` 并热重调度。

## 7. 前端架构

前端为 React/TypeScript 单页应用，不使用 React Router；`App.tsx` 通过 History API 和 `parseRoute()` 实现路由。支持根路径和后端托管时的 `/ui` base。

当前路由：

- `/`、`/chat`（均进入聊天页）
- `/tasks`、`/tasks/:taskId`
- `/agents`、`/agents/:agentId`
- `/trace`、`/trace/:traceId`
- `/wells`、`/wells/:wellId`
- `/reports`
- `/params`
- `/las/import`
- `/artifacts`
- `/settings/{skills|providers|scheduler|plugins|mcp|channels|security}`

其中 `/reports`、`/params`、`/las/import` 可通过地址直接访问，但当前不在顶栏导航项中；它们不是不存在的页面，也不应被描述为顶栏可见入口。会话历史由聊天页侧栏 `ChatHistoryPanel` 条件渲染，没有 `/chats` 或 `/chats/:threadId` 独立路由。

API 基址固定为相对路径 `/api/v1`。Console JWT 同时通过 HttpOnly cookie 和 localStorage Bearer 使用；同源部署由浏览器自动携带 cookie，分离开发部署需要正确配置代理/CORS/凭据。

## 8. 持久化布局

默认根目录由 `WORKSPACE_DIR` 决定，默认是 `backend/workspace`：

```text
workspace/
├─ agents/{agent_id}/
│  ├─ files/                         # Workspace FilesystemBackend
│  ├─ skills/                        # 工作区技能副本
│  └─ skills_state.json              # 技能启停
├─ checkpoints/
│  └─ agent-{agent_id摘要}.sqlite3    # 每 Agent 独立 LangGraph checkpoint
├─ sessions/{thread_id}.json         # 会话
├─ tasks/task_queue.sqlite3       # 持久化任务队列（WAL）
├─ tasks/task_history.json        # 旧 JSON 历史（迁移源，不自动删除）
├─ plans/plan_history.json           # 计划审计
├─ security/approval_history.json    # 审批审计
├─ gateway/message_history.json      # 渠道消息，最近 500 条
├─ access_control.json               # 渠道白名单
├─ domain/
│  ├─ domain_data.json               # 井/井段/日报/参数/LAS 索引
│  ├─ las_uploads/                   # 上传原文件
│  └─ las_curves/{las_id}.json       # LAS 曲线与质量数据
├─ charts/                           # PNG 产物
├─ code/                             # 代码产物
├─ artifacts/{kind}_{filename}.json  # 产物侧车元数据
└─ .cache/
   ├─ traces.jsonl                   # Trace 事件
   ├─ cron_jobs.json                 # Cron Job
   ├─ cron_history.json              # Cron 运行历史（上限 500）
   └─ capabilities.json              # Provider 能力缓存
```

其他持久化位置：

- `backend/.env`：Provider 默认值/API Key/base URL、插件启停、`HEARTBEAT_*` 等配置；
- `backend/skills`：全局技能池；
- `backend/plugins_ext`：插件目录；
- `backend/AGENTS.md`：文件型记忆源。

不持久化或仅部分持久化：

- 显式 `CHECKPOINT_BACKEND=memory` 时的 LangGraph checkpoint；
- `InMemoryStore` 长期记忆；
- API/渠道/Provider 限流窗口；
- 已加载 Workspace 注册表和 Agent 实例（磁盘发现可重建列表元数据）；
- `RunRegistry` 中进行中的任务与运行（只在当前进程存在，重启后不能恢复或继续取消）。

Checkpoint SQLite schema 由官方 saver `setup()` 向前初始化。领域 `domain_data.json` 使用 `schema_version=1`、进程内 `RLock`、写前 `.bak` 和同目录临时文件 `fsync + os.replace`，兼容旧无版本 JSON；这不提供跨进程锁或数据库 migration。其他 JSON/JSONL Store 仍按各自实现读写。

## 9. 安全边界

### 9.1 HTTP API

- `/api/v1` 在存在用户库、或配置 `API_TOKEN`/`CONSOLE_PASSWORD` 后受保护。
- 接受 Bearer API Token、`X-API-Token`、Console 会话 JWT Bearer/cookie。
- `/api/v1/monitor/health` 和 `/api/v1/auth/*` 豁免。
- 限流按 actor/token 摘要优先、IP 兜底，状态仅在当前进程。
- CORS 来源由 `CORS_ORIGINS` 配置。
- 资源授权失败统一 404（防枚举）；权限决策基于服务端 actor，不信任客户端 user ID。

### 9.2 Console 与团队身份

无用户且未配置 `API_TOKEN`/`CONSOLE_PASSWORD` 时为开放模式。空用户库可通过本机或 `BOOTSTRAP_TOKEN` 创建首个 owner。用户密码 Argon2id；会话 JWT 含 `user_id/role/token_version/session_id`，SQLite WAL（`identity_sqlite_path`）持久化会话与授权。系统角色 `owner/admin/operator/viewer`；Agent/知识库支持 `private|workspace` 与 `viewer|editor|runner` ACL。Cookie 写请求校验 CSRF；`API_TOKEN`/`CONSOLE_PASSWORD` 保持兼容。无 MFA、无租户/SSO。

### 9.3 工具与文件

- ToolGuard 是 Agent 工具调用前的应用层控制。
- Agent Workspace 使用不同文件根；技能、插件和文件 API 进行路径归一化检查。
- 这不是 OS 级隔离。运行服务的系统用户权限、容器挂载、网络出口与外部命令能力仍决定最终风险。
- Provider 密钥持久化到明文 `.env`，生产环境应依赖外部 Secret 管理和最小文件权限。

### 9.4 渠道

渠道入口在 Agent 前执行白名单与用户限流。路由已调用各渠道 `verify_signature`（未配密钥时 `skipped`）；真实回发仍依赖凭据与平台网络。部署时不能把“路由存在/单元测试通过”等同于“真实平台联调已完成”。

## 10. 部署拓扑

### 10.1 后端单镜像

Dockerfile 的 `backend-runtime` 会先构建前端，再复制到 `/app/frontend_dist`。Uvicorn 监听 8000，FastAPI 同时提供 API、`/docs` 和 `/ui`。健康检查调用 `/api/v1/monitor/health`。

### 10.2 Compose 默认拓扑

```text
Browser :5173
   │
   ▼
Nginx frontend
   ├─ static React
   ├─ /api/* ─────────▶ backend:8000
   ├─ /docs ──────────▶ backend:8000/docs
   └─ /openapi.json ──▶ backend:8000/openapi.json

backend
   ├─ bind mount workspace
   ├─ bind mount skills
   └─ bind mount plugins_ext

ollama:11434（可选 profile）
```

Compose 中 frontend 和 backend 是两个容器；backend 镜像自身仍包含 `/ui`，因此存在两种前端入口。默认都为单副本、本地卷。

### 10.3 本地开发

- 后端：Uvicorn 8000。
- 前端：Vite 常用 5173，并通过项目代理/同源路径访问 `/api/v1`。
- 外部 Provider、MCP 和渠道按 `.env` 配置。

## 11. 已知限制与演进方向

1. **恢复性边界**：SQLite 已支持单实例跨重启；多实例共享恢复仍需 PostgreSQL/协调层，memory 降级不支持跨重启。
2. **任务取消边界**：`RunRegistry` 已提供单进程 `asyncio.Task`/令牌取消与安全终态，但不是持久化可靠队列，不支持跨进程、多副本或重启后的活动运行取消。
3. **流式取消边界**：前端停止先 abort 再调用服务端取消 API，SSE 断连也会尽力取消；网络中断下客户端仍可能拿不到服务端确认结果。
4. **Workspace 生命周期**：磁盘列表发现与可选 purge 已闭环；idle eviction 未调度；`.purged` 标记仅用于 resume 语义，不恢复工作区内容。
5. **存储可靠性**：DomainStore 已增强单实例原子写和备份，但 JSON/JSONL 仍不适合高并发和多实例；事务数据库与迁移仍属未来。
6. **调度可靠性**：Cron history 已单机落盘；APScheduler 多副本仍会重复触发。
7. **安全模型**：单实例单工作区多用户 RBAC 已落地；无租户/SSO/自定义角色；插件是进程内代码；ToolGuard 不是沙箱。
8. **限流语义**：Provider 限流位于模型解析入口，不覆盖每次模型请求。
9. **领域完整性**：关联 CRUD 和井依赖 409 已实现；无数据库外键、跨进程事务、批量操作和乐观并发版本。
10. **国际化**：主要是中文 UI，zh/en 只覆盖命令和部分安全提示。
11. **可观测后端**：Prometheus 文本和本地 Trace 可用，但缺默认集中日志、OTLP exporter 与告警配置。
12. **外部集成**：Provider、MCP、渠道能否真实工作取决于凭据、网络和第三方 API，不应仅按代码路由判定可用。
