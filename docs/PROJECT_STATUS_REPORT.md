# BoetClaw 项目状态报告

> 修订日期：2026-07-20  
> 评估口径：以当前源码、配置和本轮可执行验证为准；计划勾选和历史文档仅作辅助证据。  
> 状态含义：**已完成**＝当前代码存在且主要路径有验证；**部分完成**＝主体存在但关键语义、入口或测试未闭环；**未闭环**＝存在接口/文案/页面外观，但不能完成其宣称的运行效果。

## 1. 执行摘要

BoetClaw 已形成可构建、可运行的单机型智能体控制台：后端具有 FastAPI API、DeepAgents/LangGraph Agent、工具与技能、多 Agent 工作区、Provider、渠道、调度、插件、领域数据、产物和可观测模块；前端具有 History API 路由、聊天、任务、Agent、Trace、设置、井数据、日报、参数、LAS 和产物页面。

但当前不能表述为“所有闭环完成”或“生产就绪”。PLAN-100—420 语义/质量项、PLAN-500 文档治理与 PLAN-600—700 运维闭环已完成；仍须保留的边界是：

1. PLAN-100/120：工具审批单实例闭环；跨资源崩溃窗口不承诺 exactly-once。
2. PLAN-110：每 Agent 独立 SQLite checkpoint；仅单机，不是多实例方案。
3. PLAN-130：多 Agent 计划 API/隔离已测；仍为单实例。
4. PLAN-200/210：同步/SSE 统一与单进程取消已闭环；不支持跨进程/重启后取消。
5. PLAN-300：单实例领域 CRUD 已闭环；无数据库事务/多实例一致性。
6. PLAN-400/410/420：Vitest 29、E2E 8（fake）、CI workflow 已落盘；云端 Actions 待启用；真实 Provider/渠道仍 manual。
7. PLAN-500：本轮文档治理闭环已完成（可持续再执行）。
8. PLAN-600—710：Cron history、Heartbeat 持久、渠道路由验签、插件扫描删除、Agent 磁盘发现/purge、idle 逐出、会话删除/归档、产物删除及 SHA256、LAS 上传门禁已完成；RBAC/多实例/真实联通默认门禁等仍未排期。

## 2. 本轮验证结果

| 验证项 | 结果 | 说明 |
|---|---|---|
| 后端 pytest | 通过 | 2026-07-20 全量执行 `213 passed`；命令：`.\.venv\Scripts\python.exe -m pytest -q` |
| 后端 lint/type | 通过 | 2026-07-20：`ruff check`、`mypy app`（`backend/pyproject.toml` 软门禁） |
| OpenAPI breaking | 通过 | 2026-07-20：`scripts/check_openapi_breaking.py` vs `openapi.snapshot.json` |
| 前端构建 | 通过 | 2026-07-20：`tsc -b && vite build`，Vite 成功输出 bundle |
| 前端 Vitest / coverage | 通过 | 2026-07-20：`npm test -- --run` 5 files / 29 passed；`npm run test:coverage` 门槛通过 |
| Docker Compose 配置 | 通过 | 2026-07-20：`docker compose config --quiet` 退出码 0 |
| 依赖审计 | 通过 | 2026-07-20：`pip-audit` 无已知漏洞；`npm audit --omit=dev --audit-level=high` 为 0 |
| GitHub Actions 云端 | 未跑 | workflow 已落盘；Git 已初始化，推送到 `NO1117/boetclaw` 并启用 Actions 后验证 |
| 真实 Provider/LLM | 未验证 | 未使用真实 API Key 或本地模型执行完整 Agent 对话；E2E manual 套件未跑 |
| 真实渠道回发 | 未验证 | 未使用钉钉、飞书、QQ、Telegram 真实凭据 |
| 浏览器 E2E | 通过（fake） | 2026-07-20：`npm run test:e2e` Chromium 8 passed（`@playwright/test` 1.61.1）；真实 Provider 为 `test:e2e:manual` |

以上结果证明当前代码的单元/集成回归、类型编译和 Compose 语法可通过，并覆盖真实最小 LangGraph 工具审批与单机 SQLite 重建恢复；不证明生产容量、外部平台联通、真实模型语义、多实例恢复或跨资源/分布式 exactly-once。

## 3. 总体完成度

| 领域 | 状态 | 结论 |
|---|---|---|
| 后端基础与模块装配 | 已完成 | FastAPI 生命周期、Agent 工厂、中间件、路由和 JSON/JSONL 存储均已落地 |
| 同步聊天 | 已完成（默认 Agent） | 默认 Agent 同步路径可处理命令、普通消息和 `/plan` |
| Plan 确认 | 已完成（单实例） | 完整 ref、严格 pending/resolver、历史筛选和多 Agent SQLite/API 重建恢复已测 |
| ToolGuard 审批 | 已完成（单实例） | 真实 graph approve 一次/reject 零次、稳定审批 key、并发互斥、失败终态和 SQLite 重建恢复已测；不保证跨资源 exactly-once |
| 多 Agent | 已完成（单实例） | 工作区、文件、同步/SSE、计划/审批恢复、磁盘列表发现、tombstone/purge 与 idle 定时逐出已闭环 |
| 流式聊天 | 已完成（单进程） | SSE v1、default/Workspace、命令/语言/source/session/interrupt、前端解析与服务端取消已统一 |
| 任务生命周期 | 已完成（单进程） | 创建、查询、重跑、状态持久化、底层协程取消、幂等和终态保护已实现 |
| 调度与渠道运维 | 部分完成 | Cron history/Heartbeat 持久与路由验签已闭环；真实回发联调、多副本调度未排期 |
| 领域数据与 UI | 已完成（单实例 CRUD） | 关联实体 API/UI CRUD、井依赖 409、原子写和关联导航已完成；数据库/多实例不在范围 |
| 可观测与审计 | 部分完成 | Trace/metrics/历史与单机 checkpoint 已落盘；集中后端和多实例协调仍缺 |
| 前端产品壳 | 已完成（首版） | 路由和主要管理页面存在且可构建 |
| 前端自动化测试/CI | 已完成（workflow 落盘） | Vitest/E2E/CI 已建立；云端 Actions/required checks 待远程启用 |
| 部署 | 部分完成 | Docker/Compose/Nginx、安装脚本和单机 SQLite checkpoint 存在；不具备多实例 HA |

## 4. 后端状态

### 4.1 已完成

- FastAPI 应用与两阶段生命周期已落地：`backend/app/main.py`、`backend/app/core/startup.py`。
- Agent 工厂能够装配默认子 Agent、工具、技能、中间件、Provider、Store 和 checkpointer：`backend/app/core/agent_factory.py`。
- 中间件栈包含可观测、PlanGate 和 ToolGuard：`backend/app/middleware/`。
- 模块化 API 覆盖 Agent、任务、Cron、Agent 工作区、技能、Provider、插件、MCP、渠道、安全、领域、文件、认证和监控：`backend/app/api/routes/`。
- 任务、会话、计划历史、审批历史、渠道历史、Trace、Cron job/history、领域对象等已有 JSON/JSONL 落盘实现；Heartbeat 配置写入 `.env`；相关路径分布于 `backend/app/memory/`、`backend/app/security/approval.py`、`backend/app/services/`、`backend/app/domain/`、`backend/app/core/observability.py`。
- API Token/Console JWT、按 token/IP API 限流、渠道白名单/用户限流、渠道路由验签、技能/插件扫描和插件默认禁用已实现：`backend/app/middleware/api_security_mw.py`、`backend/app/security/`、`backend/app/services/gateway/`、`backend/app/skills_system/`、`backend/app/plugins/`。

### 4.2 部分完成与风险

- 数据存储以单进程 JSON/JSONL 为主。`backend/app/domain/store.py` 的读改写没有数据库事务或跨进程锁；适合 MVP/单机，不适合多副本并发写。
- Python 依赖多数只有下限约束；`langgraph-checkpoint-sqlite==3.1.0` 已单独锁定，但整体仍缺 Python lock/哈希固定。
- Provider 限流位于模型解析入口，不是每次 LLM `invoke/ainvoke` 的真实请求限流：`backend/app/providers/rate_limiter.py`、`manager.py`。
- 外部 Provider、MCP 和渠道的真实凭据路径未在本轮验证；测试中的 fake/mock 成功不应外推为生产联通。

## 5. 审批 resume 语义

### 5.1 已实现的部分（PLAN-100/110/120）

- ToolGuard 创建带 approval ID 的 payload 并调用 `interrupt({"type": "tool_approval", ...})`：`backend/app/middleware/tool_guard_mw.py`。
- API 提供待审批、历史和恢复入口：`backend/app/api/routes/security.py`。
- Agent invoke 从真实 Interrupt 生成 `ExecutionRef` 并绑定审批；恢复由 `approval_resume.py` 经共享 adapter 使用 `Command(resume=decision)`。
- 恢复前校验 approval ID、pending、ref、interrupt type 和 decision；裁决原子进入 `resuming`，成功后才写 approved/rejected，失败写不可自动重试的 `resume_failed/error`。
- 中断异常不再默认 approve，受保护 handler 不执行；旧缺 ref 历史只读。
- PLAN-110 提供默认 SQLite checkpoint、每 Agent 独立 DB 和 registry 丢失后的 resolver 重建；恢复前从 checkpoint task 校验 interrupt ID/type。
- PLAN-120 以 `agent/thread/tool_call` 稳定 key 复用节点重放审批，单进程并发裁决只有一个进入 graph；真实 LangGraph 测试证明 approve handler 一次、reject 零次，并覆盖 SQLite 服务/adapter 重建和非默认 Agent resolver。

### 5.2 边界

1. SQLite 与进程内锁只覆盖单实例，不提供多实例共享裁决协调。
2. 审批 JSON、checkpoint 与工具外部资源没有共同事务；副作用完成后、终态写回前进程崩溃会产生结果不确定窗口。
3. `resume_failed` 为安全优先终态，不自动重试；该策略降低重复副作用风险，但不构成跨资源或分布式 exactly-once。

结论：PLAN-120 在声明的单实例范围内闭环；上述崩溃边界必须保留。PLAN-130 也已完成，但不改变工具副作用边界。

## 6. 多 Agent 与计划确认

### 6.1 已完成的部分

- `MultiAgentManager` 为每个工作区创建独立 `FilesystemBackend`，并从 `CheckpointProvider` 获取该 Agent 专属 SQLite saver；每 Agent 锁负责懒加载；`list_agents` 扫描磁盘并跳过 tombstone：`backend/app/agents/multi_agent_manager.py`、`backend/app/core/checkpoint.py`。
- 删除默认写 tombstone；`purge=true` 清工作区目录并经 `CheckpointProvider.purge` 清理 checkpoint：`backend/app/api/routes/agents.py`。
- 同步聊天在 `agent_id != default` 时路由到工作区 Agent：`backend/app/api/routes/agent.py`、`backend/app/agents/runtime.py`。
- 前端可创建、切换、查看并选择仅注销/彻底清除：`frontend/src/App.tsx`、`frontend/src/components/AgentSwitcher.tsx`。

### 6.2 计划确认实现与边界

- `PlanConfirmRequest`、响应、历史和前端 pending 均传递服务端完整 `ExecutionRef`；仅唯一 default pending 保留 thread-only 限期兼容。
- 同步非默认调用和 resume 共用严格 resolver；底层 adapter 在 registry 丢失时按 ref 重建原 graph，并从 SQLite 验证 interrupt。
- 精确 pending 历史、checkpoint、Agent 和 interrupt type 任一不匹配均返回 4xx；tombstone/purge 后 resume 409，未知 Agent 仍 404，不回退 default。
- 真实最小 LangGraph + SQLite/API 测试覆盖两个 Workspace 同 thread 的 approve/edit/reject、伪造 ref、history 筛选、reload/evict/provider 重建、删除/未知 Agent 和 default 兼容。

结论：多 Agent 普通同步聊天、SSE、Plan 确认与按 Agent/thread 隔离的运行取消已在单实例范围内闭环。

## 7. 流式路径

### 7.1 已完成

- 同步/SSE 共用 `prepare_chat()`，统一 thread、严格 Agent resolver、source、body lang/`Accept-Language`、slash command 与 trace/run。
- default 与 Workspace 均对目标 graph 使用 `astream(..., stream_mode=["messages", "updates"], subgraphs=True)`；`/plan` 在两路径统一清洗并进入规划态。
- SSE v1 JSON data envelope 包含 `event/data/version/thread_id/agent_id/trace_id/run_id`，事件明确为 update/interrupt/command/done/error；done 只发一次。
- 成功与中断各写一轮会话；命令不进 LLM 且不写会话，运行错误不写会话。
- 前端使用 `fetch` + `ReadableStream`，纯函数 parser 处理多行 data、CRLF、任意分块边界和旧结构；不再强制 `/plan`/非默认 Agent 同步，中断复用 PlanConfirm/ApprovalCard。
- `test_plan200_stream_chat.py` 覆盖 default/nondefault、plan/command/lang/source/session/error/done once；TypeScript 与 Vite 构建通过。
- 同步/SSE run 登记到 `RunRegistry`；`POST /agent/runs/cancel` 校验 run/Agent/thread 后取消并等待，前端停止按钮先 abort 再请求服务端确认。

### 7.2 剩余边界

- 注册表和取消令牌只在当前进程有效；多副本、进程崩溃或服务重启后不能继续取消原活动运行。
- 网络断开时服务端会尽力取消 SSE run，但客户端不一定收到确认响应。
- PLAN-400 已建立 Vitest/jsdom/Testing Library；SSE parser 和独立 `chatStream.ts` 协议模块具备多行/CRLF/分块/error/done once/abort+服务端取消测试及覆盖率门槛。

结论：PLAN-200/210 已统一同步、流式和单进程取消语义；PLAN-400 已补齐关键前端协议与组件自动化证据。

## 8. 任务与取消

### 8.1 已完成

- 任务支持创建、列表、详情、重跑和取消 API：`backend/app/api/routes/tasks.py`。
- 状态、结果、Trace/run 和 metadata 写入 JSON；重启时把原 `running` 任务标记为 failed：`backend/app/services/task_scheduler.py`。
- 前端任务页支持筛选、详情、重跑、取消和 Trace 跳转：`frontend/src/components/TaskMonitor.tsx`、`frontend/src/App.tsx`。
- `RunRegistry` 以 Agent/thread/run/task 四类标识跟踪 `asyncio.Task` 与令牌，并审计 pending/running/cancelling/cancelled/completed/failed 转换。
- `POST /tasks/{id}/cancel` 取消底层协程并等待确认；重复取消幂等，已完成/失败明确 409，CAS 防止 cancelled 被后续结果覆盖。
- `/stop` 严格定位同 Agent+thread 的活动 run；流取消 API 支持 run 精确校验，不会误取消同 thread 的其他 Agent。
- `test_plan210_cancellation.py` 覆盖长运行 Agent、竞态、隔离、重复取消、interrupt 和清理。

### 8.2 剩余边界

- 注册表是单进程内存协调，不是可靠任务队列；多副本需要共享运行协调和持久化 worker。
- 服务重启会把遗留 running/cancelling JSON 状态标记为 failed，不能恢复或继续取消原协程。

## 9. API 状态

### 9.1 已完成

当前路由源码至少覆盖：

- Agent：同步/流式聊天、计划确认与历史、会话、工具、Trace。
- Tasks：任务、Cron、Heartbeat。
- Management：Agents、Skills、Providers、Plugins、MCP。
- Security/Auth：Guard 配置、审批、API Token、Console JWT。
- Gateway：四渠道 webhook、状态、白名单、消息历史、重试。
- Domain/Files：井、井段、日报、参数、LAS、产物预览与下载。
- Monitor：health、stats、events、timeline、Prometheus metrics。

事实路径：`backend/app/api/routes/*.py`。

### 9.2 文档与契约风险

- `docs/API.md` 已按当前 Router 重建为完整人工索引，但仍需随运行时 OpenAPI 和路由变更持续维护。
- 没有自动化 OpenAPI 契约快照或 schema diff。
- 多个 API 将所有异常转换为 HTTP 500 并返回 `str(exc)`，错误类型和外部信息暴露需进一步治理。
- JSON 文件写入接口缺少数据库级并发控制；多 worker/多副本部署风险高。

## 10. 页面与前端状态

### 10.1 已完成

- `frontend/src/App.tsx` 实现轻量 History API 路由，不再是只有模态 Tab 的旧状态。
- 现有路径包括 `/chat`、`/tasks/:id`、`/agents/:id`、`/trace/:id`、`/wells/:id`、`/reports`、`/params`、`/las/import`、`/artifacts` 和多个 `/settings/*`。
- 管理组件覆盖技能、Provider、Cron、插件、MCP、渠道、审批等：`frontend/src/components/`。
- Nginx 对未知页面回退 `index.html`，支持前端深链：`deploy/nginx.conf`。

### 10.2 部分完成

- 路由是 `App.tsx` 内手写解析和大量条件渲染，不是成熟路由库；页面逻辑集中在单文件，维护和测试成本较高。
- 许多 API 调用直接 `fetch()` 且没有统一错误、认证头、重试和请求取消层。当前同源 HttpOnly cookie 能覆盖已登录场景，但跨域/token-only 场景不完整。
- 前端没有错误边界、系统化表单校验和无障碍测试材料。
- 构建产物主 JS 约 420 KB，当前规模可接受但没有按路由拆包。

## 11. 领域 CRUD UI

### 11.1 已完成

- 领域模型和 JSON 存储已实现：`backend/app/domain/models.py`、`store.py`。
- 井、井段、日报、钻井参数和 LAS 记录均提供完整单条 CRUD；LAS 另支持路径导入、上传解析与质检，上传前校验扩展名/大小/`~Curve/~A` 段标记：`backend/app/api/routes/domain.py`。
- 关联实体创建/更新在进程内锁中校验井存在；井有关联领域记录或产物时删除返回 409，不静默产生孤儿。
- 前端井详情支持编辑/删除、井段管理和关联导航；日报、参数、LAS 页面支持井筛选、详情/编辑、删除确认和错误展示：`frontend/src/App.tsx`、`frontend/src/services/api.ts`。
- `query_drilling_params` 能读取领域存储，并保留无数据时 fallback：`backend/app/tools/builtin.py`。

### 11.2 边界

- 删除井默认拒绝依赖而非级联；批量导入/删除和乐观并发版本不在本项。
- DomainStore 的锁仅限当前进程，不能协调多进程或多副本。
- `schema_version=1` 和旧无版本 JSON 兼容不是数据库 migration；其他 JSON/JSONL Store 尚未统一原子写。
- 领域更新/删除请求已有 Vitest 行为断言；井/日报 CRUD 与 `well_id` 深链已有 Playwright fake E2E；参数/LAS 页未纳入默认 E2E。

结论：PLAN-300 的单实例领域 CRUD 与导航闭环已完成；跨进程锁、数据库事务/迁移仍是边界。前端关键自动化已由 PLAN-400/410 补齐，不代表全部领域页高覆盖。

## 12. 测试与 CI

### 12.1 已完成

- `backend/tests/` 有 36 个测试文件、213 项 pytest 用例（2026-07-20 全量 `213 passed`）。
- 测试覆盖核心中间件、技能、多 Agent、Provider、渠道验签、调度/Cron history/Heartbeat、插件扫描删除、Agent 磁盘/purge、会话归档、可观测、领域、LAS、产物、安全、持久化和访问控制。
- 前端 Vitest 5 files / 29 passed、关键协议覆盖率门槛、Playwright Chromium E2E 8 passed（fake Provider，2026-07-20）。
- PLAN-420：`.github/workflows/ci.yml`、OpenAPI 快照/breaking 检查、ruff/mypy、pip-audit/npm audit、可选 gitleaks、本地 `scripts/ci-local.*` 已落地；本机等价门禁通过。

### 12.2 未闭环 / 边界

- 云端 GitHub Actions 与 branch protection required checks 尚未在远程仓库实际启用（Git 已初始化，待 push 至 `NO1117/boetclaw`）。
- 默认 E2E/CI 不证明真实 LLM、MCP、四渠道联通；见 `npm run test:e2e:manual`。
- 镜像 CVE 扫描未做阻断门禁；gitleaks 默认非阻断。
- 取消证据限于单进程 fake Agent，不覆盖跨进程、多副本或重启后活动运行。

结论：后端/前端自动化与 CI workflow 文件已具备；发布前仍需远程启用 Actions，并单独做真实集成验收。

## 13. 部署状态

### 13.1 已完成

- `Dockerfile` 提供前端构建、后端运行和 Nginx 前端三阶段。
- `docker-compose.yml` 提供 backend、frontend 和可选 Ollama，并挂载 workspace、skills、plugins。
- `deploy/nginx.conf` 提供 API 反代和 SPA fallback。
- Windows、Linux/macOS 安装脚本存在。

### 13.2 风险

- 当前拓扑是单实例/本地卷，LangGraph checkpoint 使用本地 SQLite；不含业务事务数据库、持久任务队列、多实例共享 checkpoint、分布式锁和高可用设计。
- Nginx 配置没有 TLS、安全头、SSE 专用缓冲/超时参数；生产环境需外层网关补齐。
- Python 依赖多数未完整锁定（仅 checkpoint SQLite 依赖已固定），基础镜像使用浮动 tag；缺 SBOM 和漏洞扫描。
- 健康检查只证明 HTTP 端点可达，不证明 Provider/MCP/渠道均可用。
- Docker Compose 语法通过不等于本轮执行了完整 `up` 和浏览器验收。

## 14. Checkpoint 持久化现状

PLAN-110 已完成单机 checkpoint 闭环：

- `backend/requirements.txt` 锁定 `langgraph-checkpoint-sqlite==3.1.0`。
- `CheckpointProvider` 统一管理 `AsyncSqliteSaver` 初始化、官方 `setup()`、按 Agent 锁和连接关闭；默认 backend 为 `sqlite`。
- 默认 Agent 与 Workspace Agent 均获取 Agent 专属 saver；数据库文件按 `agent_id` 摘要隔离，相同 thread 不跨 Agent 串线。
- reload、idle eviction 和注销 Agent 实例不删除 checkpoint。adapter registry 丢失时 resolver 可重建 graph，并读取 checkpoint tasks 校验 interrupt ID/type。
- startup/lifespan/health 已接入；SQLite 初始化失败时 health 降级且 Agent 不就绪。`memory` 只允许显式降级并报告不支持跨重启。
- 会话、计划和审批 JSON 仍只是展示/审计数据，不能替代 LangGraph checkpoint。

边界：SQLite 是单机方案，不支持多个后端副本共享恢复、锁协调或 HA；数据库清理、迁移和多实例方案仍需后续设计。PLAN-120 已完成单实例工具审批闭环，但跨资源崩溃窗口不保证 exactly-once；PLAN-130 已完成多 Agent 计划 API/隔离验收。

## 15. 风险优先级与建议闭环顺序

### P0：语义正确性与安全

1. PLAN-100 已完成统一 ref、恢复服务拆分、状态顺序与 fail-closed。
2. PLAN-110 已完成单机 SQLite checkpoint 与重建恢复基础。
3. PLAN-120 已完成工具 handler approve 单次执行、reject 不执行、并发幂等和非默认 Agent resolver。
4. PLAN-130 已完成相同 thread 多 Workspace 的计划 API 往返与完整隔离验收。

### P1：执行生命周期

1. PLAN-210 已将任务执行改为可追踪 `asyncio.Task`，取消时发送取消信号并防止完成状态覆盖。
2. PLAN-210 已使 `/stop` 绑定 Agent/thread/run，前端流停止执行本地 abort 后再请求服务端确认。
3. PLAN-400 已为 SSE parser、流式取消和计划/审批关键交互建立 25 项前端自动化测试。

### P2：产品与工程质量

1. Vitest + Testing Library 与 Playwright Chromium E2E（fake Provider）已完成。
2. PLAN-420 CI workflow 已落盘；下一动作是推送远程、跑通 Actions，并按 `DEPLOYMENT.md` 启用 required checks。
3. 可选补强镜像 CVE 扫描（如 Trivy）与将 gitleaks 升为 required（观察期后）。
4. 保持 OpenAPI 快照与 `docs/API.md` 人工索引同步。
5. 将 JSON 存储演进为具备事务和迁移的数据库，并明确单实例到多副本的运行边界。

## 16. 最终判断

截至 2026-07-20，BoetClaw 可定义为：

- **后端功能面较完整、后端回归测试可通过的单机 MVP/演示系统**；
- **具有首版管理控制台和钻井领域数据入口**；
- **不应定义为所有业务闭环完成**；
- **可定义为具备单机 SQLite checkpoint 重启恢复基础，但不应定义为多实例 HITL 或 HA 系统**；
- **可定义为具备单进程执行级取消、单实例领域 CRUD、运维持久/验签/插件与 Agent 治理、关键前端组件/协议测试、fake-Provider 浏览器 E2E，以及已落盘的 CI workflow**；
- **不应宣称跨进程/重启后取消、数据库事务、真实第三方联通，或云端 Actions/branch protection 已在远程启用**。

下一阶段：推送远程并启用 CI required checks；真实 Provider/渠道联调仍为 manual。RBAC/多实例/数据库事务等见 `IMPLEMENTATION_PLAN.md`「不在本轮落地范围」。文档侧按 PLAN-500/650 清单在契约或验证基线变化时再跑一轮治理。
