# BoetClaw 验收清单

> 基线：2026-07-20。  
> 目的：建立 `REQ-* → FUN-* → API → PAGE → TEST/证据 → PLAN-*` 的可追溯验收链。  
> 契约真源：当前源码与运行实例 `/openapi.json`；本文只记录验收状态与证据索引。

## 1. 状态与证据定义

- `[x] 已完成`：入口、服务、数据/副作用和查询/UI 主路径存在，并有当前自动化或可重复构建证据。
- `[~] 部分完成`：主体存在，但关键语义、恢复、路由、CRUD、外部联通或自动化证据未闭环。
- `[ ] 未完成`：当前没有对应实现或没有足以支持完成结论的证据。
- `TEST-*`：本文件定义的证据编号，不代表仓库已有同名测试文件。
- `PAGE-*`：前端路由验收编号；“无页面”不等于 API 不可用。
- `PLAN-*`：未闭环项的当前落地计划；`—` 表示已完成基线或明确不在本轮排期。

现有通用证据：

| 证据 | 内容 | 状态 |
|---|---|---|
| TEST-BE-001 | 2026-07-20 项目虚拟环境后端 pytest：全量 `213 passed` | [x] |
| TEST-BE-200 | PLAN-200 ASGI/fake Agent：6 collected，覆盖同步/SSE 编排与 envelope | [x] |
| TEST-BE-210 | `test_plan210_cancellation.py`：7 项，覆盖底层取消、隔离、幂等、竞态、`/stop`、run API、interrupt 与清理 | [x] |
| TEST-BE-300 | `test_plan300_domain_crud.py`：10 项，覆盖关联 CRUD/404/409、LAS 文件策略、旧 JSON、备份/原子写和并发 | [x] |
| TEST-BE-100 | `test_plan100_execution_ref.py`：10 项 ref/恢复安全专项测试 | [x] |
| TEST-BE-110 | `test_plan110_checkpoint.py`：11 项 SQLite checkpoint/重建恢复专项测试 | [x] |
| TEST-BE-130 | `test_plan130_multi_agent_plan.py`：真实 LangGraph + SQLite/API 多 Agent 计划专项测试 | [x] |
| TEST-FE-001 | `frontend` 执行 `npm run build`，TypeScript/Vite 通过 | [x] |
| TEST-DEP-001 | `docker compose config --quiet` 退出码 0 | [x] |
| TEST-FE-002 | Vitest 5 files/29 tests；SSE/流协议覆盖率门槛通过（2026-07-20） | [x] PLAN-400 |
| TEST-E2E-001 | Playwright Chromium 关键流程 E2E（fake Provider；`@playwright/test` 1.61.1；8 tests；2026-07-20 复验 8 passed） | [x] PLAN-410 |
| TEST-CI-001 | 实际 CI workflow（`.github/workflows/ci.yml`）与本地等价门禁；required checks 启用步骤已文档化 | [x] PLAN-420（云端 Actions 待仓库启用） |
| TEST-EXT-001 | 真实 Provider/LLM 联调 | [ ] 未排期 |
| TEST-EXT-002 | 四渠道真实 webhook、验签与回发联调 | [ ] 未排期 |

## 2. 需求—功能—接口—页面—证据—计划总表

### 2.1 Agent、计划与会话

| 状态 | 需求 | 功能 | API 路径 | PAGE 路由 | TEST/证据 | 后续计划 |
|---|---|---|---|---|---|---|
| [x] | REQ-100 | FUN-001 同步对话 | `POST /api/v1/agent/chat` | PAGE-001 `/chat` | TEST-BE-001、TEST-FE-001 | PLAN-001 |
| [x] | REQ-101、REQ-108 | FUN-002 SSE 流式对话 | `POST /api/v1/agent/chat/stream` | PAGE-001 `/chat` | TEST-BE-200；TEST-FE-002 覆盖多行/CRLF/分块/error/done once/停止取消 | PLAN-200、PLAN-400（已完成） |
| [x] | REQ-102 | FUN-003 Plan 门控 | `POST /api/v1/agent/chat`（`/plan` 前缀） | PAGE-001 `/chat` | `test_phase2_plan.py` | PLAN-001 |
| [x] | REQ-103、REQ-107、REQ-108 | FUN-004 计划确认 | `POST /api/v1/agent/plan/confirm` | PAGE-002 `/chat` 内条件渲染的 PlanConfirm，无独立路由 | TEST-BE-130：双 Workspace 同 thread、三种决策、重建/删除/错误 ref/default 兼容 | PLAN-130（已完成） |
| [x] | REQ-103 | FUN-005 计划审计 | `GET /api/v1/agent/plan/history` | 无独立页面 | 计划历史 JSON 测试；TEST-BE-130 联合筛选 | PLAN-130（已完成） |
| [x] | REQ-104 | FUN-006 会话列表/恢复/导出/删除/归档 | `GET/POST/DELETE /api/v1/agent/sessions*` | PAGE-001 `/chat` 侧栏 ChatHistoryPanel，无独立深链 | `test_phase14_sessions.py` 覆盖删除与归档过滤；`api.test.ts` 覆盖 DELETE/归档契约；TEST-E2E-001（对话路径） | PLAN-410、PLAN-670、PLAN-710（已完成） |
| [x] | REQ-105 | FUN-007 Slash 命令 | `POST /api/v1/agent/chat` | PAGE-001 `/chat` | TEST-BE-210：`/stop` 同 Agent/thread 定位、跨 Agent 隔离和无运行响应 | PLAN-210（已完成） |
| [~] | REQ-106、REQ-310 | FUN-007、FUN-125 | chat body `lang`、`Accept-Language` | 全部页面 | 命令与 ToolGuard zh/en 测试；UI/Agent 输出未全量覆盖 | 未排期 |
| [x] | REQ-107 | FUN-003、004、063 | 计划/审批 resume 基础 | PAGE-002、PAGE-014 | TEST-BE-110：默认 SQLite、Agent 重建、checkpoint interrupt 校验；memory 显式不支持 | PLAN-110（已完成） |

### 2.2 工具、扩展、技能与多 Agent

| 状态 | 需求 | 功能 | API 路径 | PAGE 路由 | TEST/证据 | 后续计划 |
|---|---|---|---|---|---|---|
| [x] | REQ-120 | FUN-020 内置工具 | `GET /api/v1/tools`、Agent 调用 | PAGE-015 `/trace/:traceId` 可观察 | 多个后端工具/产物测试 | PLAN-001 |
| [x] | REQ-121、REQ-122 | FUN-008、FUN-021 子 Agent/工具组装 | Agent 内部 | 无配置页面 | Agent factory 测试 | PLAN-001 |
| [x] | REQ-123 | FUN-022、FUN-023 MCP | `/api/v1/tools/mcp/*` | PAGE-010 `/settings/mcp` | `test_phase15_mcp.py`；真实 MCP 未验证 | PLAN-001 |
| [x] | REQ-124、REQ-125 | FUN-024、FUN-025 插件 | `/api/v1/plugins*`（含 scan/scan-report/DELETE） | PAGE-009 `/settings/plugins` | `test_plan630_plugin_scan_delete.py` + `test_phase10_plugins.py`（2026-07-17） | PLAN-630（已完成） |
| [x] | REQ-140—REQ-142 | FUN-040—FUN-044 技能 | `/api/v1/skills*` | PAGE-006 `/settings/skills` | `test_phase4_skills.py` | PLAN-001 |
| [x] | REQ-143 | FUN-045—FUN-047 Agent 管理/隔离/删除 | `/api/v1/agents*`（含 `purge`） | PAGE-004 `/agents`、`/agents/:agentId` | `test_plan640_agent_disk_purge.py`：tombstone/purge/default 拒绝 | PLAN-640（已完成） |
| [x] | REQ-144 | FUN-048 Agent 历史聚合 | `GET /api/v1/agents/{agent_id}/files`、`GET /api/v1/agents/{agent_id}/history` | PAGE-004 | `test_phase17_agent_index.py` | PLAN-001 |
| [x] | REQ-145 | FUN-045、FUN-049 Workspace 恢复/逐出 | `/api/v1/agents` | PAGE-004 | 磁盘列表发现 + TEST-BE-130 定向 resolver/逐出；PLAN-660 接入 idle 生命周期调度 | PLAN-640、PLAN-660 |

### 2.3 安全与身份

| 状态 | 需求 | 功能 | API 路径 | PAGE 路由 | TEST/证据 | 后续计划 |
|---|---|---|---|---|---|---|
| [x] | REQ-160 | FUN-060、FUN-061 ToolGuard/Guardian | `GET/PUT /api/v1/security/config` | PAGE-014 `/settings/security` | `test_phase3_security.py` | PLAN-001 |
| [x] | REQ-161 | FUN-062 工具人工审批 | `/api/v1/security/approvals*` | PAGE-014 | `test_plan120_tool_approval.py`：真实 graph approve 一次、reject 零次、重放/并发幂等、非默认 resolver | PLAN-120（已完成） |
| [x] | REQ-162、REQ-107 | FUN-063 审批持久化 | `GET /api/v1/security/approvals/history` | PAGE-014 | SQLite 重建恢复；失败/处理中重启为不可自动重试终态；memory 显式过期 | PLAN-110、PLAN-120（已完成） |
| [x] | REQ-163、REQ-164 | FUN-064—FUN-066 API Token/JWT | `/api/v1/auth/*`；其余 `/api/v1/*` | PAGE-016 条件渲染登录页，无独立路由 | `test_phase23_api_security.py` | PLAN-001 |
| [x] | REQ-165 | FUN-067、FUN-068 渠道白名单/限流 | `/api/v1/gateway/access-control` | PAGE-011 `/settings/channels` | `test_phase25_gateway_access_control.py` | PLAN-001 |
| [x] | REQ-166 | FUN-087 渠道 webhook 安全 | `/api/v1/gateway/*/webhook` | PAGE-011 | `test_plan620_webhook_signature.py`：配置密钥强制验签、未配置 `skipped`、中间件豁免 | PLAN-620（已完成）；真实平台联调仍见 TEST-EXT-002 |
| [ ] | REQ-167、REQ-020 | FUN-069 RBAC/租户 | — | — | 无用户/角色/租户模型 | 不在本轮范围 |

### 2.4 任务、调度与渠道

| 状态 | 需求 | 功能 | API 路径 | PAGE 路由 | TEST/证据 | 后续计划 |
|---|---|---|---|---|---|---|
| [x] | REQ-180（创建/查询/重跑部分） | FUN-080、FUN-081 | `/api/v1/tasks*` | PAGE-005 `/tasks`、`/tasks/:taskId` | 任务路由/持久化代码、TEST-FE-001 | PLAN-001 |
| [x] | REQ-180（取消） | FUN-082 | `POST /api/v1/tasks/{id}/cancel` | PAGE-005 | TEST-BE-210：CancelledError、幂等、终态保护、完成后 409 | PLAN-210（已完成） |
| [x] | REQ-181 | FUN-083 任务历史恢复 | `/api/v1/tasks` | PAGE-005 | `test_phase24_task_persistence.py` | PLAN-001 |
| [x] | REQ-182 | FUN-084、FUN-085 Cron | `/api/v1/tasks/cron*` | PAGE-008 `/settings/scheduler` | `test_plan600_cron_history.py`：`cron_history.json` 跨重启可查、上限 500 | PLAN-600（已完成） |
| [x] | REQ-183 | FUN-086 Heartbeat | `/api/v1/tasks/heartbeat` | PAGE-008 | `test_plan610_heartbeat_persist.py`：`.env` 落盘与热重调度 | PLAN-610（已完成） |
| [~] | REQ-184 | FUN-087、FUN-088 四渠道/队列/回发 | `/api/v1/gateway/*/webhook` | PAGE-011 | payload/队列/路由验签已测；真实回发与 fallback 背压未闭环 | PLAN-620（验签已完成）；真实联调未排期 |
| [x] | REQ-185 | FUN-089 渠道运维 | `/api/v1/gateway/status|messages*` | PAGE-011 | `test_phase15_gateway_ops.py` | PLAN-001 |

### 2.5 钻井领域与产物

| 状态 | 需求 | 功能 | API 路径 | PAGE 路由 | TEST/证据 | 后续计划 |
|---|---|---|---|---|---|---|
| [x] | REQ-200 | FUN-100 井 CRUD | `/api/v1/domain/wells*` | PAGE-020 `/wells`、`/wells/:wellId` | TEST-BE-300；井编辑/删除确认、依赖 409 可见 | PLAN-300（已完成） |
| [x] | REQ-201 | FUN-101 井段管理 | `/api/v1/domain/sections*` | PAGE-020 井详情内 | 单条 GET、完整 CRUD、井详情编辑/删除 | PLAN-300（已完成） |
| [x] | REQ-202 | FUN-102、FUN-103 日报/参数 | `/api/v1/domain/reports|params` | PAGE-021 `/reports`、PAGE-022 `/params` | TEST-BE-300；TEST-FE-002；TEST-E2E-001 覆盖日报 CRUD/深链 | PLAN-300、PLAN-400、PLAN-410（已完成） |
| [x] | REQ-203 | FUN-104、FUN-105 LAS | `/api/v1/domain/las-files|las/import|las/upload` | PAGE-023 `/las/import` | CRUD、上传/解析、上传扩展名/大小/内容门禁、托管文件安全删除、井筛选 | PLAN-300、PLAN-700（已完成）；LAS 浏览器路径未纳入默认 E2E |
| [x] | REQ-204、REQ-205 | FUN-107—FUN-109 产物 | `/api/v1/files/artifacts*` | PAGE-024 `/artifacts` | artifact/meta 测试含删除和 SHA256；`api.test.ts` 覆盖 DELETE 与 checksum 契约；TEST-FE-001 | PLAN-001、PLAN-680、PLAN-690（已完成） |
| [x] | REQ-206、REQ-309（单实例领域 JSON） | FUN-106 关系/原子存储 | 领域写接口 | PAGE-020—024 | TEST-BE-300：锁、备份、replace、旧 JSON、孤儿保护 | PLAN-300（已完成）；数据库/多实例不在本项 |

### 2.6 可观测、部署与工程质量

| 状态 | 需求 | 功能 | API 路径 | PAGE 路由 | TEST/证据 | 后续计划 |
|---|---|---|---|---|---|---|
| [x] | REQ-220、REQ-221 | FUN-120、FUN-121 Trace/timeline | `/api/v1/agent/trace*`、`GET /api/v1/monitor/trace/{trace_id}/timeline` | PAGE-015 `/trace/:traceId` | `test_phase12_observability.py` | PLAN-001 |
| [x] | REQ-222 | FUN-122、FUN-123 health/stats/metrics | `GET /api/v1/monitor/health`、`/api/v1/monitor/stats`、`/api/v1/monitor/metrics` | 监控侧栏/Trace 页 | observability/metrics 测试 | PLAN-001 |
| [x] | REQ-223 | FUN-124 OTel/LangSmith | 应用内部 | 无专页 | OTel 幂等测试 | PLAN-001 |
| [ ] | REQ-224 | FUN-120、FUN-124 集中可观测 | — | — | 无集中日志/OTLP/告警验收 | 不在本轮范围 |
| [x] | REQ-300、REQ-307 | FUN-127—FUN-129 启动/部署 | `/api/v1/monitor/health`、`/ui` | 全部 SPA 路由 | TEST-BE-001、TEST-FE-001、TEST-DEP-001 | PLAN-001 |
| [~] | REQ-303 | FUN-010、FUN-083、FUN-085、FUN-106 | 多个存储 API | 多页面 | checkpoint、Cron history、多类 JSON 可恢复；`InMemoryStore` 仍不跨重启 | PLAN-110/600（已完成）；Store memory 未排期 |
| [ ] | REQ-305、REQ-021 | FUN-131 多实例/数据库 | — | — | checkpoint 仅单机 SQLite；无多实例共享队列、锁或事务数据库 | 不在本轮范围 |
| [x] | REQ-308 | FUN-130 OpenAPI | `/docs`、`/openapi.json` | Swagger UI | FastAPI 运行时生成；TEST-CI-001 OpenAPI breaking | PLAN-420（已完成）；文档索引维护属 PLAN-500 |
| [x] | 工程质量门禁 | FUN-125、FUN-130 | 全部公开 API | 全部页面 | TEST-FE-002、TEST-E2E-001、TEST-CI-001 | PLAN-400、PLAN-410、PLAN-420 已完成；真实 Provider/渠道仍 manual |
| [x] | 文档可追溯治理 | FUN-130 | 人工索引与验收映射 | 文档导航 | DOCUMENT_INVENTORY / ACCEPTANCE / STATUS 与代码一致；本轮 PLAN-500 闭环 | PLAN-500（本轮已完成；可持续再执行） |

## 3. 接口维度验收

### 3.1 已有主路径

- [x] API-001 应用提供 `/docs` 和 `/openapi.json`。
- [x] API-002 业务 Router 统一挂载 `/api/v1`。
- [x] API-003 同步聊天返回 thread/trace/run 和 Agent 标识。
- [x] API-004 任务、会话、计划历史、审批历史、领域数据和 Trace 有查询入口。
- [x] API-005 health 免鉴权限流，Token/JWT 保护其他 `/api/v1` 路径。
- [x] API-006 领域井 API 具备完整 REST CRUD。

### 3.2 部分/未完成契约

- [x] API-100 流式 chat 统一使用 `agent_id/source/lang` 与 `Accept-Language`，返回版本化 SSE envelope，并支持 command/interrupt/done/error；PLAN-200 已验收。
- [x] API-101 `PlanConfirmRequest`、响应和历史携带完整 `ExecutionRef`；支持 Agent+thread 历史筛选，唯一 default pending 保留 thread-only 限期兼容；PLAN-130 已验收。
- [x] API-102 审批恢复请求和新记录绑定 Agent/thread/namespace/interrupt，旧缺 ref 只读；PLAN-120 真实 graph 端到端已完成。
- [x] API-103 task cancel 取消底层协程并等待确认，重复取消幂等，终态安全；PLAN-210 已验收。
- [x] API-104 sections/reports/params/las 具备单条详情与完整 CRUD；关联写 404、井依赖删除 409 明确。PLAN-300 已验收。
- [x] API-105 OpenAPI breaking-change 检查：`backend/scripts/check_openapi_breaking.py` + `openapi.snapshot.json`（删 operation / 新增必填 / 删 2xx 失败）。

## 4. 页面维度验收

| 页面 | 路由 | 状态 | 当前证据 | 主要缺口/计划 |
|---|---|---|---|---|
| PAGE-001 聊天与会话侧栏 | `/`、`/chat` | [x] | 两个路径均进入聊天页；同步/SSE 支持 default/Workspace、计划/审批中断、停止与会话；侧栏支持删除/归档；TEST-FE-002、TEST-E2E-001 | 会话无独立深链 |
| PAGE-002 计划确认 | `/chat` 内条件渲染，无独立路由 | [x] | PlanConfirm 保存原响应 ref，切换 Agent 后仍恢复原图且错误可见；TEST-BE-130、TEST-FE-002、TEST-E2E-001 | — |
| PAGE-004 Agent | `/agents`、`/agents/:agentId` | [x] | 创建、切换、详情、文件/历史；删除确认支持仅注销/彻底清除；purge 后 resume 409；idle 定时逐出已接入生命周期 | 单进程内存逐出，不代表跨实例生命周期 |
| PAGE-005 任务 | `/tasks`、`/tasks/:taskId` | [x] | 筛选、详情、重跑、取消按钮；服务端取消底层协程并等待确认；TEST-E2E-001 覆盖深链取消 | — |
| PAGE-006 技能 | `/settings/skills` | [x] | 安装、详情、编辑、删除、扫描 | 技能页交互未纳入默认 E2E |
| PAGE-007 Provider | `/settings/providers` | [x] | 配置、模型、检测、默认切换 | 密钥管理/Agent 重建边界未排期 |
| PAGE-008 调度 | `/settings/scheduler` | [x] | Cron/Heartbeat 管理；history/config 持久化已闭环 | PLAN-600/610 |
| PAGE-009 插件 | `/settings/plugins` | [x] | 安装、详情、启停、扫描报告、删除确认 | PLAN-630；静态扫描非沙箱 |
| PAGE-010 MCP | `/settings/mcp` | [x] | server/tool/reload 管理 | 真实服务联调未验证 |
| PAGE-011 渠道 | `/settings/channels` | [~] | 状态、白名单、历史、重试；路由验签已接入 | 真实平台回发联调未排期 |
| PAGE-014 安全 | `/settings/security` | [x] | Guard、待审批、历史；TEST-FE-002 覆盖 pending/resuming/不可恢复、失败和重复点击；TEST-E2E-001 覆盖深链刷新 | — |
| PAGE-015 Trace | `/trace/:traceId` | [x] | timeline、耗时、分类 | 大数据分页未排期 |
| PAGE-016 登录 | 按认证状态条件渲染，无独立路由 | [x] | 配置 Console 密码后，未认证访问任意前端路径均显示 LoginPage | 无账户、RBAC、锁定或 MFA；定位本地单用户 |
| PAGE-020 井 | `/wells`、`/wells/:wellId` | [x] | 创建/详情/编辑/删除确认、井段 CRUD、到日报/参数/LAS/产物的带井筛选导航；TEST-E2E-001 覆盖创建 | — |
| PAGE-021 日报 | `/reports?well_id=` | [x] | 新增、井筛选、详情/编辑、删除确认、错误可见；TEST-FE-002、TEST-E2E-001 | — |
| PAGE-022 参数 | `/params?well_id=` | [x] | 新增、井筛选、详情/编辑、删除确认、错误可见，CRUD 后保留筛选 | 批量导入未排期；参数页未纳入默认 E2E |
| PAGE-023 LAS | `/las/import?well_id=` | [x] | 路径导入、上传门禁、质检、记录详情/编辑/删除确认和井筛选 | LAS 页未纳入默认 E2E |
| PAGE-024 产物 | `/artifacts` | [x] | 筛选、预览、下载、删除、SHA256 摘要 | 保留策略未排期 |

关键协议与组件已有 TEST-FE-002；关键浏览器路径已有 TEST-E2E-001（fake Provider）。其余页面仍缺少深度组件覆盖；真实 Provider/渠道联调不在默认 E2E 门禁内。

## 5. P0/P1 专项验收门

### 5.1 审批恢复

- [x] 新可恢复审批绑定 agent/thread/显式 namespace/interrupt ID。
- [x] 恢复前校验 pending 与身份一致。
- [x] 恢复成功后才写 approved/rejected，失败写 resume_failed/error。
- [x] approve 工具只执行一次，reject 从不执行。
- [x] interrupt 异常不默认批准，handler 不执行。
- [x] SQLite provider/默认 Agent 重建后可读取并恢复 checkpoint interrupt。
- [x] 默认/非默认 Agent resolver、真实工具流程、重复/并发裁决均有测试。
- **状态**：PLAN-120 已完成；跨资源崩溃窗口不承诺 exactly-once。

### 5.2 多 Agent 计划确认

- [x] PlanConfirm request/response/history 全链路携带 agent ID。
- [x] checkpoint 层相同 thread ID 在不同 Agent DB 间隔离。
- [x] approve/edit/reject 恢复原 Workspace graph。
- [x] resolver 可在 registry 丢失后重建 Workspace graph 并校验持久 interrupt。
- [x] 完整 API 往返、删除语义及多 Workspace 计划隔离验收。
- **状态**：PLAN-130 已完成（单实例）；该项当时不含的流式路径已由 PLAN-200 完成。

### 5.3 流式统一

- [x] stream 使用与同步相同的 Agent resolver 和请求预处理。
- [x] `/plan`、slash command、source、lang、session 行为一致。
- [x] SSE 纯解析器支持多行 data、CRLF、分块边界和旧结构；后端覆盖 done once/error，前端网络提前断流明确报错。
- [x] 非默认 Agent 不再强制降级同步。
- **状态**：PLAN-200、PLAN-400 已完成；纯解析器和流协议已有自动化单测。

### 5.4 真正取消

- [x] 保存可取消运行句柄/令牌。
- [x] task cancel、`/stop` 和流停止绑定正确 run。
- [x] 取消后协程停止，状态不被完成结果覆盖。
- [x] 重复取消和完成/取消竞态有测试。
- **状态**：PLAN-210、PLAN-400、PLAN-410 已完成；2026-07-20 基线：后端全量 213 passed、前端 Vitest 5 files/29 passed、E2E 8 passed（fake Provider）；跨进程、多副本及重启后取消不在本项范围。

### 5.5 前端测试与 CI

- [x] `npm test -- --run` 存在并通过。
- [x] 计划、审批、流式、取消、领域表单有组件测试。
- [x] Playwright 关键流程在 fake Provider/隔离 store 下通过（Chromium）。
- [x] CI workflow 覆盖后端 pytest/lint/type、前端 test/coverage/build、E2E、Compose、OpenAPI breaking、pip-audit/npm audit；本地可用 `scripts/ci-local.*` 复现。
- **状态**：PLAN-400、PLAN-410、PLAN-420 已完成。云端 Actions / branch protection required checks 需在推送 GitHub 后启用（见 `DEPLOYMENT.md`）。真实 Provider/渠道仍非默认门禁。

## 6. 未排期项映射（保持未完成）

下列项在 `IMPLEMENTATION_PLAN.md`「不在本轮落地范围」中明确保留，**不得**为抬高完成率改为 `[x]`：

| 状态 | 需求/主题 | 说明 | 映射 |
|---|---|---|---|
| [ ] | REQ-020 / REQ-167 / FUN-069 | 多用户、RBAC、租户、SSO | 不在本轮范围 |
| [ ] | REQ-021 / REQ-305 / FUN-131 | 多实例、共享队列、事务数据库 | 不在本轮范围；checkpoint 仅为单机 SQLite |
| [ ] | REQ-022 | 生产密钥库/轮换/字段加密 | 不在本轮范围 |
| [ ] | REQ-023 / REQ-024 / REQ-224 | WITSML、原生移动端/更多渠道、集中可观测后端 | 不在本轮范围 |
| [ ] | TEST-EXT-001 / TEST-EXT-002 | 真实 Provider/LLM、四渠道真实验签与回发 | 未排期；仅 `test:e2e:manual` |
| [~] | 渠道真实回发联调等 | 路由验签/队列主体已完成；真实回发缺口明确 | 表内对应行标「未排期」；PLAN-600—700 运维项已完成 |

## 7. 验收维护规则

1. REQ/FUN/API/PAGE 任一状态变化时同步更新本文件。
2. `[~]` 只能在缺口和 PLAN 清楚时使用；不能为了“完成率”改成 `[x]`。
3. 新增 API 后先检查运行时 OpenAPI，再更新人工索引和本映射。
4. TEST 证据必须注明执行日期、环境和是否使用 fake/mock。
5. 真实 Provider、MCP、渠道或生产环境未执行时，相关条目保持 `[~]` 或 `[ ]`。
6. PLAN-500 文档治理完成后，验证基线数字与未排期项映射须与 `TESTING.md`、`DOCUMENT_INVENTORY.md` 一致。
