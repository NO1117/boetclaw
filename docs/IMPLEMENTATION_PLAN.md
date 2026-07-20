# BoetClaw 项目落地计划书

> 计划基线：2026-07-17。  
> 事实依据：当前源码、运行时 OpenAPI、`PROJECT_STATUS_REPORT.md`、`REQUIREMENTS.md`、`FEATURE_CATALOG.md` 和 `TESTING.md`。  
> 本文件只保留当前有效计划。完整 v3 计划历史已归档至 `archive/2026-07-15/IMPLEMENTATION_PLAN_v3_full.md`。  
> 状态定义：**已完成基线**仅说明当前已有能力或本轮文档工作已完成；**待实施**表示代码缺口仍然存在，不能据计划文字宣称已实现。

## 1. 落地目标与原则

BoetClaw 当前是后端功能面较完整、可构建的单机 MVP。下一阶段不再扩张功能清单，优先修复人工中断恢复、Agent 路由、流式一致性和执行取消等语义正确性问题，再补齐领域 CRUD、前端自动化测试和 CI。

执行原则：

1. 代码与运行时 `/openapi.json` 是事实真源，计划勾选不能替代验收证据。
2. 安全和恢复性缺口优先于新功能；失败必须显式呈现，禁止 fail-open。
3. 计划确认与工具审批分离建模，但共享统一的 `(agent_id, thread_id, checkpoint_ns)` 运行标识。
4. 同步、流式、后台任务和渠道入口复用同一运行编排层，避免语义继续分叉。
5. 每个计划项必须同时具备自动化测试、失败场景、回滚方案和文档更新。
6. 当前仍以单实例为目标；多租户、HA、分布式队列不在本轮范围。

## 2. 已完成基线

### PLAN-001 当前系统事实基线

- **状态**：已完成基线
- **范围**：FastAPI/DeepAgents/LangGraph 后端、React 控制台、工具/技能/插件/MCP、四渠道、Cron/Heartbeat、领域数据、产物、Trace/Prometheus、Docker/Compose。
- **证据**：`PROJECT_STATUS_REPORT.md`；2026-07-17 后端全量 pytest `213`（`--collect-only`）；Vitest `26`；Playwright E2E `8`（fake，沿用既有记录）；`npm run build` 与 `docker compose config --quiet` 通过；CI workflow 已落盘；PLAN-600—710 运维闭环已完成。
- **边界**：已证明单机 SQLite checkpoint 重建恢复基础、进程内执行级取消、单实例领域 CRUD、运维持久/验签/插件与 Agent 治理与 fake E2E；不证明真实 Provider/渠道联通、多实例 HITL、审批副作用恰好一次、跨进程取消、云端 Actions 已启用或生产就绪。

### PLAN-002 现行文档体系基线

- **状态**：已完成基线
- **范围**：材料台账、状态报告、需求、功能、架构、API、测试、安全、渠道、部署、导航、计划、进度与验收映射。
- **证据**：`docs/README.md`、`DOCUMENT_INVENTORY.md` 及本轮实现记录。
- **边界**：文档只描述当前事实；API 字段与状态码仍以运行实例 OpenAPI 为准。

### PLAN-003 已验证工程基线

- **状态**：已完成基线
- **范围**：后端 pytest、TypeScript/Vite 构建和 Compose 语法检查。
- **证据**：`TESTING.md` 与 `PROJECT_STATUS_REPORT.md`。
- **边界**：当时仓库没有前端测试套件和实际 CI workflow；PLAN-400/410/420 已补齐。

## 3. 阶段总览

| 阶段 | 计划 | 优先级 | 状态 | 主要依赖 |
|---|---|---:|---|---|
| 阶段 A：恢复语义校正 | PLAN-100、PLAN-110、PLAN-120、PLAN-130 | P0 | 已完成（2026-07-16） | PLAN-001 |
| 阶段 B：执行路径统一 | PLAN-200、PLAN-210 | P1 | 已完成（2026-07-16） | 阶段 A 的运行标识与恢复接口 |
| 阶段 C：领域产品闭环 | PLAN-300 | P2 | 已完成（2026-07-16） | API 契约稳定 |
| 阶段 D：质量门禁 | PLAN-400、PLAN-410、PLAN-420 | P1/P2 | 已完成 | 阶段 A-C 可测试接口 |
| 阶段 E：文档治理 | PLAN-500 | P1 | 本轮闭环已完成（可持续再执行） | 所有代码与契约变更 |
| 阶段 F：运维闭环 | PLAN-600—PLAN-710 | P1 | 已完成（2026-07-17） | PLAN-001、阶段 E |

推荐关键路径：

```text
PLAN-100 → PLAN-110 → PLAN-120 → PLAN-130
                         ├→ PLAN-200 → PLAN-210
                         └→ PLAN-400 → PLAN-410 → PLAN-420
PLAN-300 ───────────────────────────────┘
PLAN-500 贯穿全部阶段（本轮闭环已完成；契约/基线变化时再执行）
PLAN-600 → … → PLAN-700 → PLAN-710（运维闭环已完成）
```

## 4. 阶段 A：恢复语义校正

### PLAN-100 统一可恢复运行标识

- **状态**：已完成（2026-07-16）
- **优先级**：P0
- **关联需求/功能**：REQ-103、REQ-107、REQ-108、REQ-161；FUN-004、FUN-062、FUN-063
- **目标**：为计划与审批建立明确的 `agent_id + thread_id + checkpoint_ns + interrupt_id` 标识，并拆分计划恢复与工具审批恢复语义。
- **依赖**：PLAN-001。

执行步骤：

1. 定义不可变 `ExecutionRef`/请求 schema；计划确认和审批记录均保存 `agent_id`、`thread_id`、checkpoint namespace 与 interrupt 标识。
2. 从 LangGraph 运行配置获取真实线程和命名空间，禁止由前端猜测或使用空字符串。
3. 将 `confirm_plan()` 拆分为计划恢复服务和工具审批恢复服务；两者共享底层 graph resume adapter，但分别记录审计。
4. 恢复前校验审批仍为 pending、请求身份与记录一致；恢复成功后再更新 approved/rejected。
5. 恢复失败写入独立 failed 状态和错误摘要，不污染计划历史，不把异常当批准。
6. 更新 Pydantic schema、OpenAPI、前端 API 类型及错误展示。

验收标准：

- 新中断返回并持久化 `agent_id`、`thread_id`、interrupt ID 和显式 namespace；根图 namespace 明确为 `""`。
- 错误 Agent、线程、审批 ID 或非 pending 状态返回明确 4xx，且不调用 graph resume。
- resume 失败时审批不显示 approved；审计中可见失败原因。
- 计划确认和工具审批分别有 API/服务测试，生产路径不存在 `interrupt()` 异常默认 approve。

实现结果与边界：

- 已增加不可变 `ExecutionRef`、真实 LangGraph Interrupt/字典 mock 安全解析、同步默认/Workspace Agent 中断响应，以及计划/审批独立恢复服务。
- 恢复前校验完整 ref、interrupt type、pending 状态；审批只在 graph resume 成功后写 approved/rejected，失败写 `resume_failed/error`。
- 旧 default-agent thread-only 请求兼容一个周期；旧审批/计划 JSON 可读，缺 ref 的审批不可恢复。
- ToolGuard 和 PlanGate 不再吞掉 `interrupt()` 异常，受保护 handler 不会因中断失败而执行。
- 本项原本不包含持久 checkpoint；该能力后由 PLAN-110 完成。工具 handler 端到端单次执行后由 PLAN-120 完成；完整多 Agent 计划 API 隔离验收仍属于 PLAN-130。
- 验证：本项完成当时后端全量 `159 passed`；前端 `npm run build` 通过。

回滚方案：

- 保留旧字段读取兼容一个迁移周期，但新写入只使用新结构。
- 若新恢复适配器异常，可关闭新恢复入口并返回“不可恢复”，不得回退为自动批准。
- 审批 JSON 变更前备份；迁移脚本可把新字段忽略后恢复旧版只读历史。

### PLAN-110 Checkpoint 持久化

- **状态**：已完成（2026-07-16）
- **优先级**：P0
- **关联需求/功能**：REQ-107、REQ-303；FUN-003、FUN-004、FUN-010、FUN-063、FUN-131
- **目标**：用持久化 LangGraph checkpointer 替换默认 Agent 和 Workspace Agent 的 `MemorySaver`，支持进程重启、Agent reload 和空闲驱逐后的中断恢复。
- **依赖**：PLAN-100 的运行标识；确定 SQLite（单机）或 PostgreSQL（多实例演进）选型。本阶段默认采用 SQLite 单实例方案。

执行步骤：

1. 增加 checkpoint 配置、依赖锁定和统一 `CheckpointProvider` 生命周期。
2. 默认 Agent 与所有 Workspace Agent 复用持久化 saver 工厂，按 `agent_id` 隔离 namespace。
3. 设计数据库路径、初始化、schema 升级、备份和关闭流程；不得把连接对象散落在 Agent 构建代码中。
4. 调整 reload/evict：释放 Agent 实例但保留 checkpoint；删除 Agent 时明确“仅注销”与“清除 checkpoint/磁盘”两种语义。
5. 提供 MemorySaver 到持久 saver 的安全切换说明；历史 JSON 审计不伪装成 checkpoint 迁移。
6. 增加跨进程重启测试：创建 interrupt、关闭服务/重建 Agent、继续 resume。

验收标准：

- 默认与 Workspace Agent 均接入持久 saver；registry 丢失时 resolver 可重建对应 graph 并校验 checkpoint interrupt。
- 技能 reload 和 idle eviction 不清理 checkpoint，同一 `(agent_id, thread_id)` 的持久状态仍可读取。
- 不同 Agent 使用相同 thread ID 时 checkpoint 不串线。
- 数据库损坏、锁冲突或初始化失败时 health 明确降级，恢复接口不得自动批准。

实现结果与边界：

- 已锁定 `langgraph-checkpoint-sqlite==3.1.0`，新增统一 `CheckpointProvider` 管理 `AsyncSqliteSaver` 的初始化、官方 `setup()`、按 Agent 并发锁和 lifespan 关闭。
- 默认 `CHECKPOINT_BACKEND=sqlite`；每个 Agent 使用基于 `agent_id` 摘要命名的独立 SQLite DB。默认 Agent 与 Workspace Agent 均从 provider 获取 saver，reload、idle eviction 和注销实例不会清理 checkpoint。
- `GraphResumeAdapter` 在进程内 registry 丢失时可按 `ExecutionRef.agent_id` 重建默认或 Workspace Agent，并从 checkpoint tasks 中核对 interrupt ID/type；缺失、已完成、类型不符或原 Agent 不存在均返回 409。
- startup、lifespan 和 `/api/v1/monitor/health` 已接入 provider；初始化失败时 health 降级且 Agent 不就绪。`memory` 仅可显式配置，并报告 `supports_restart_resume=false`，不做 SQLite 故障后的隐式回退。
- 专项测试覆盖 provider/Agent 重建恢复、同 thread 跨 Agent 数据库隔离、连接关闭、非法 backend、memory 降级、缺失/伪造 interrupt 和审批 pending 重启策略；本项完成当时后端全量 `159 passed`，前端 `npm run build` 通过。
- 本项完成的是单实例 SQLite checkpoint 与恢复基础。SQLite 不是多实例方案；审批真实执行/拒绝/幂等后由 PLAN-120 完成，多 Agent 计划 API 与隔离验收后由 PLAN-130 完成。

回滚方案：

- 配置支持临时切回 `memory`，但 health 和 UI 必须明确显示“不支持跨重启恢复”。
- 迁移前备份 checkpoint 数据库；schema 升级使用向前迁移，不执行不可逆删除。
- 新 saver 故障时停止接受新的可恢复中断，保留同步普通对话降级能力。

### PLAN-120 工具审批端到端恢复

- **状态**：已完成（2026-07-16）
- **优先级**：P0
- **关联需求/功能**：REQ-003、REQ-161、REQ-162；FUN-060—FUN-063
- **目标**：完成“风险发现—审批记录—图中断—人工裁决—原工具调用恢复—审计”的安全闭环。
- **依赖**：PLAN-100、PLAN-110。

执行步骤：

1. ToolGuard 创建审批时写入完整 `ExecutionRef` 和风险快照。
2. 中断 payload、审批记录、前端卡片和恢复请求使用同一 approval/interrupt ID。
3. 审批恢复按 Agent 路由到对应 graph；拒绝时保证工具 handler 未执行。
4. 删除 fail-open 分支；中断不可用时返回安全错误 ToolMessage 或使运行失败。
5. 增加幂等裁决：重复 approve/reject 不重复执行工具。
6. 覆盖默认/非默认 Agent、批准/拒绝、恢复失败、重启恢复和并发重复提交测试。

验收标准：

- 审批卡展示真实 Agent/线程/工具/参数/风险。
- approve 只执行一次原工具，reject 从不执行。
- 服务重启后 pending 审批可恢复；checkpoint 缺失时显示不可恢复并保留审计。
- 自动化测试使用真实 LangGraph 中断流程，而非仅 monkeypatch 默认批准。

实现结果与边界：

- ToolGuard 以服务端 `agent_id + thread_id + tool_call_id` 生成稳定 key；LangGraph 从节点开头重放时复用同一 pending/resuming 审批，不生成重复 pending。
- 审批状态机为 `pending→resuming→approved|rejected`，恢复失败为不可自动重试的 `resume_failed`；单进程锁保证重复/并发裁决只有一个请求进入原 graph，且保留 PLAN-100 的“graph 成功后才写 approved/rejected”。
- 恢复前校验 approval ID、完整 ExecutionRef、interrupt type、pending/resumable 和 decision；adapter 按 ref 恢复 Agent/thread 上下文，并通过 resolver 支持默认及非默认 Agent。拒绝路径不调用 handler，中断不可用继续 fail-closed。
- ApprovalCard 展示 Agent/thread/tool/参数/风险/ref/状态/错误，缺 ref、处理中及终态禁用，提交集合防止重复点击。
- `test_plan120_tool_approval.py` 使用真实最小 LangGraph interrupt/resume 覆盖 approve 一次、reject 零次、节点重放不重复审批、重复/并发裁决、失败终态、服务/adapter 重建后 SQLite 恢复及非默认 Agent resolver；本项完成当时全量后端 `159 passed`，前端 build 通过。
- 边界：本地审批 JSON、LangGraph SQLite 与工具写入的外部资源不共享事务。若进程在工具副作用完成后、graph 返回或审批状态写回前崩溃，结果可能不确定；系统选择终止自动重试以降低重复副作用风险，但不提供跨资源或分布式 exactly-once。

回滚方案：

- 可禁用 ToolGuard 审批型工具并改为硬拒绝，不能回退为放行。
- 保留旧审批历史只读展示；新裁决接口可通过 feature flag 停用。

### PLAN-130 多 Agent 计划确认

- **状态**：已完成（2026-07-16）
- **优先级**：P0
- **关联需求/功能**：REQ-004、REQ-103、REQ-108、REQ-143；FUN-004、FUN-045、FUN-046
- **目标**：确保非默认 Agent 的 `/plan` 中断和确认始终恢复到原 Workspace graph。
- **依赖**：PLAN-100、PLAN-110；可与 PLAN-120 后半段并行。

执行步骤：

1. `PlanConfirmRequest`、响应、计划历史和前端状态加入 `agent_id` 与 interrupt 标识。
2. 抽取统一 Agent resolver，普通调用与 resume 使用同一解析规则。
3. PlanConfirm 组件保存响应返回的 Agent 标识，不从当前下拉选择推断。
4. 编辑、批准、拒绝均路由到原 Agent；Agent 已删除/未注册时返回明确错误。
5. 增加两个 Workspace 使用相同 thread ID 的隔离测试和 API 往返测试。

验收标准：

- 非默认 Agent `/plan` 的 approve/edit/reject 均恢复原图。
- 同 thread ID 在不同 Agent 下互不影响。
- 默认 Agent 行为保持兼容；计划历史可按 Agent 和线程查询。

实现结果与边界：

- `PlanConfirmRequest` 以完整服务端 `ExecutionRef` 为主契约；响应和新计划历史显式返回/保存 `agent_id`、`thread_id`、`interrupt_id` 与完整 ref。历史支持 `agent_id + thread_id` 联合筛选，旧无 Agent 字段 JSON 按 default 兼容读取。
- 同步非默认调用和恢复共用严格 resolver；不存在、已删除或 ref 与 pending 历史/checkpoint 不匹配均返回明确 4xx。删除保留 checkpoint，但写入 tombstone，禁止残留目录被静默重建为可用 Agent。
- PlanConfirm/ChatPanel 始终保存并提交中断响应的 ref；切换当前 Agent 不改写 pending 来源，失败保留卡片并展示错误。未引入流式路径改动。
- `test_plan130_multi_agent_plan.py` 使用真实最小 LangGraph、每 Agent SQLite saver 和 ASGI API，覆盖两个 Workspace 同 thread 的 approve/edit/reject、跨 Agent 伪造 ref、history 过滤、reload/evict/provider 重建、删除/未知 Agent，以及唯一 default pending 的旧 thread-only 兼容。
- 验证：本项完成当时后端全量 `159 passed`；前端 `npm run build` 通过。流式统一后由 PLAN-200 完成。

回滚方案：

- 前端可暂时禁止非默认 Agent 使用 `/plan` 并给出说明；不得静默转到默认 Agent。
- 保留默认 Agent 旧请求兼容，但服务端对缺失 `agent_id` 只允许明确的 default 场景。

## 5. 阶段 B：执行路径统一

### PLAN-200 同步与流式统一

- **状态**：已完成（2026-07-16）
- **优先级**：P1
- **关联需求/功能**：REQ-100、REQ-101、REQ-106、REQ-108；FUN-001、FUN-002、FUN-007
- **目标**：同步与 SSE 共用命令、语言、source、Agent 路由、会话记录和中断事件编排。
- **依赖**：PLAN-100、PLAN-130。

执行步骤：

1. 抽取 `prepare_chat()` 和 Agent resolver，统一 `/plan`、slash command、语言与 source。
2. 为统一事件定义版本化 SSE envelope：`event`、`data`、`trace_id`、`run_id`、`agent_id`、`thread_id`。
3. 非默认 Agent 流式调用路由到 Workspace Agent。
4. 前端实现完整 SSE block 解析，避免重复 `onDone()`，并处理 plan/approval interrupt。
5. 统一同步/流式会话持久化和错误映射。
6. 增加后端 stream API、前端解析器与多 Agent 流式测试。

验收标准：

- 同一请求在同步/流式下具有一致的 Agent、语言、source、命令和会话结果语义。
- 非默认 Agent 可流式执行；`/plan` 不再由前端强制降级同步。
- done 只触发一次，多行 data、网络中断和 error 事件均有测试。

实现结果与边界：

- 新增最小 `prepare_chat()` 编排层，同步和 SSE 共用 thread/Agent/source/lang/trace/run、slash command 预处理与严格 Agent resolver；`/plan` 统一去前缀并注入规划态，控制命令不进入 LLM。
- 默认与 Workspace Agent 均经 `stream_agent()` 真正调用各自 graph 的 `astream`；流式结果复用同步中断收尾，注册同一 `ExecutionRef`，成功或中断仅记录一次会话，运行错误不写会话。
- SSE v1 data envelope 固定包含 `event/data/version/thread_id/agent_id/trace_id/run_id`，事件类型为 `update/done/error/interrupt/command`；成功、命令和中断均只发送一次 `done`，错误只发送 `error`。
- 前端删除 `/plan`/非默认 Agent 强制同步，发送 `agent_id/source/lang`；纯函数 SSE block 解析支持多行 data、CRLF 和任意分块边界，并兼容旧单层 SSE；中断复用 PlanConfirm/ApprovalCard，HTTP、服务事件和提前断流错误均可见。
- `test_plan200_stream_chat.py` 使用 ASGI/fake Agent 覆盖 default/nondefault、同步共享 resolver、`/plan` interrupt、slash command、lang/source、单次会话持久化、error 和 done once。该项完成时 SSE 纯解析器仅以 build 验证，后由 PLAN-400 补齐前端协议测试。
- 当时验证：后端全量 `159 passed`；前端 `npm run build` 通过。当时未实现的服务端执行取消现已由 PLAN-210 完成。

回滚方案：

- 保留旧 SSE 版本一个兼容周期，通过请求 header/配置切换。
- 新流式路径异常时前端可显式提示并让用户选择同步重试，不自动重复提交。

### PLAN-210 任务与运行真正取消

- **状态**：已完成（2026-07-16）
- **优先级**：P1
- **关联需求/功能**：REQ-105、REQ-180；FUN-002、FUN-082
- **目标**：取消实际执行，而不是只修改 JSON 状态；统一任务取消、`/stop` 和前端流停止语义。
- **依赖**：PLAN-200 的统一运行标识；PLAN-100。

执行步骤：

1. 建立 `RunRegistry`，保存 run/thread/task 与 `asyncio.Task` 或取消令牌的映射。
2. 后台任务从 FastAPI `BackgroundTasks` 迁移到可追踪执行器；定义 pending/running/cancelling/cancelled/completed/failed 状态机。
3. 取消时发出取消信号并等待确认；完成/异常写回使用 compare-and-set，不能覆盖 cancelled。
4. `/stop` 绑定当前 Agent/thread/run；无可取消运行时返回明确结果。
5. 前端暴露停止按钮：先 abort 客户端流，再调用服务端取消；显示“请求已停止”与“服务端已取消”的区别。
6. 添加长运行 fake Agent 的取消、竞态、重复取消和重启测试。

验收标准：

- 取消运行中的任务后，底层协程收到 `CancelledError` 或受控取消信号。
- cancelled 状态不会被 completed/failed 覆盖。
- `/stop`、任务页取消和流式停止均能定位正确 run；不同 Agent/thread 不串线。
- 所有状态转换有审计事件与自动化测试。

实现记录：

- **实现思路**：建立最小单进程 `RunRegistry`，统一 task、同步/SSE 和渠道 Agent 子任务的活动运行索引、取消令牌与安全状态转换；终态清理活动索引和 task 引用，并保留有界终态记录以支持明确、幂等响应。
- **修改文件**：新增 `backend/app/services/run_registry.py`、`backend/tests/test_plan210_cancellation.py`；修改 `backend/app/services/task_scheduler.py`、`backend/app/services/chat_orchestration.py`、`backend/app/api/routes/tasks.py`、`backend/app/api/routes/agent.py`、`backend/app/api/routes/gateway.py`、`backend/app/api/schemas.py`、`backend/app/main.py`、`backend/app/i18n/__init__.py`、`frontend/src/services/api.ts`、`frontend/src/components/ChatPanel.tsx`、`frontend/src/components/ChatPanel.css`，并同步现行文档。
- **核心变更**：task 自动运行/重跑改为注册表创建的受控 task；取消 API 先进入 cancelling、取消底层协程并等待 `CancelledError` 确认，重复取消幂等，已 completed/failed 返回 409，CAS 状态更新阻止 cancelled 被完成/失败覆盖。同步/SSE 和渠道 Agent 子任务也进入注册表；`/stop` 严格按 Agent+thread 选择最新活动 run，新增 `POST /api/v1/agent/runs/cancel` 支持精确取消。前端先执行 AbortController，再请求服务端确认，并区分本地停止与服务端取消结果。
- **问题与解决**：旧任务取消只修改 JSON 状态，`BackgroundTasks` 不暴露可等待执行句柄；流式本地 abort 也不能证明服务端协程已停止。解决方式是由 `RunRegistry` 统一持有 `asyncio.Task`/取消令牌，以受限状态机和 CAS 协调取消与完成竞态，并由前端在 abort 后调用服务端取消 API 获取确认。
- **验证**：`test_plan210_cancellation.py` 以长运行 fake Agent 覆盖底层 `CancelledError`、任务终态保护、Agent/thread 隔离、重复取消、完成/取消竞态、`/stop`、运行取消端点、interrupt 正常完成和 shutdown 清理。本项完成当时后端全量约 `166 passed`；现行最近基线为 2026-07-17 的 pytest `206`，前端 Vitest/E2E/build 见 PLAN-400/410。
- **该项完成时的边界**：注册表为单进程内存结构，不支持跨进程、多副本取消或重启恢复活动 task；组件测试后由 PLAN-400 完成，E2E 后由 PLAN-410 完成。

回滚方案：

- 新执行器可通过配置关闭；关闭时取消接口必须返回“不支持执行级取消”，不能伪装成功。
- 保留任务 JSON schema 向后兼容，未知新状态按 failed/needs_review 展示。

## 6. 阶段 C：领域产品闭环

### PLAN-300 领域 CRUD、关系约束与导航

- **状态**：已完成（2026-07-16）
- **优先级**：P2
- **关联需求/功能**：REQ-200—REQ-206、REQ-309；FUN-100—FUN-106
- **目标**：补齐日报、钻井参数、LAS 的详情/更新/删除，并让页面具备可发现、可编辑、可删除的完整导航。
- **依赖**：现有领域模型与 API；先确定删除/级联和 JSON 到数据库演进策略。

执行步骤：

1. 为日报、参数、LAS 增加 get/update/delete；为井段增加 get-by-id。
2. 定义井删除策略：阻止存在关联数据的删除，或显式确认级联；默认采用“有依赖则 409”。
3. 为 JSON Store 增加原子写、进程内锁、schema version 和备份；数据库迁移另立后续计划。
4. 前端服务层补齐类型与方法；页面增加详情、编辑、删除确认、错误提示和返回导航。
5. 统一 `/wells/:id` 到 sections/reports/params/las/artifacts 的关联入口与筛选。
6. 增加 API CRUD、约束、孤儿数据、页面交互和回归测试。

验收标准：

- 所有领域实体至少具备 create/list/get/update/delete，或有明确不可变理由。
- 删除井不会静默留下孤儿记录；冲突返回 409 并在 UI 解释。
- 用户可从井详情到相关日报、参数、LAS 和产物，并可返回原筛选上下文。
- 测试覆盖正常 CRUD、缺失资源、关联冲突和并发写基本场景。

实现结果与边界：

- 井段新增单条 GET；日报、参数、LAS 记录补齐 get/update/delete，关联实体创建和更新均在 Store 锁内验证 `well_id`，不存在返回结构化 404。
- 删除井会统计井段、日报、参数、LAS 和产物侧车依赖；有依赖返回结构化 409 并保留原数据。LAS 删除只清理系统管理的曲线缓存和无共享引用的上传文件，服务器路径导入的外部源文件不删除。
- `DomainStore` 新写入 `schema_version=1`，兼容读取旧无版本 JSON；写操作使用进程内 `RLock`、写前 `.bak`、同目录临时文件 `fsync + os.replace`，不引入数据库迁移或多实例协调。
- 前端 service 补齐全部方法；井详情支持编辑、删除、井段编辑/删除和关联导航，井数据页可发现日报/参数/LAS；日报、参数、LAS 支持井筛选、详情/编辑、删除确认、错误展示，来自井详情的 `well_id` 查询上下文会保留。
- `test_plan300_domain_crud.py` 10 项覆盖四类关联实体 CRUD/404、缺失井、井删除冲突、LAS 安全清理、旧 JSON、备份/原子替换失败和进程内并发写。2026-07-16 项目虚拟环境全量收集并通过 `176` 项 pytest；前端 `npm run build` 通过。
- 边界：这是单实例 JSON 可靠性增强，不提供跨进程锁、数据库事务或在线 schema migration；该项完成时组件/E2E 仍属于 PLAN-400/410，PLAN-400 后续已完成。

回滚方案：

- 破坏性删除默认 feature flag 关闭；先上线只读详情和更新。
- 写操作前自动备份 `domain_data.json`；新 schema 保留向后读取兼容。

## 7. 阶段 D：质量门禁

### PLAN-400 前端组件与协议测试

- **状态**：已完成（2026-07-16）
- **优先级**：P1
- **关联需求/功能**：REQ-101、REQ-103、REQ-161、REQ-180；FUN-002、FUN-004、FUN-062、FUN-082、FUN-125
- **目标**：建立 Vitest + Testing Library 基线，优先覆盖流式解析、计划确认、审批卡、任务取消和领域表单。
- **依赖**：PLAN-100 的 API 类型；可先覆盖稳定组件，后随 PLAN-200/210 扩展。

执行步骤：

1. 添加 test 脚本、jsdom、Testing Library 和统一 mock server/fetch 工具。
2. 测试 API/SSE 解析器、鉴权错误和 abort。
3. 测试 PlanConfirm/ApprovalCard 的 Agent/线程传递与失败状态。
4. 测试 TaskMonitor 取消竞态和领域编辑/删除确认。
5. 设置覆盖率报告，首期只对关键模块设可达门槛，避免用低价值用例刷覆盖率。

验收标准：

- `npm test -- --run` 可重复通过。
- 关键交互的成功、拒绝、网络错误和恢复失败均有断言。
- 测试不依赖真实 Provider 或渠道。

完成记录：

- 通过 npm 实际解析并锁定 Vitest `4.1.10`、jsdom `29.1.1`、Testing Library React `16.3.2`、jest-dom `6.9.1`、user-event `14.6.1` 和 coverage-v8 `4.1.10`，均只进入 `devDependencies`；新增 `test`、`test:coverage` 脚本。
- 保留纯函数 `sse.ts`，将流式 fetch/envelope/abort/服务端取消提取到最小独立 `chatStream.ts`；统一 fetch mock 支持 JSON、文本、分块流和 deferred 请求。
- 5 个测试文件共 25 项覆盖 SSE 多行、CRLF、分块、flush、无效 JSON、done once、error/中断；计划完整 ExecutionRef 与失败可见；审批 pending/resuming/不可恢复、重复点击与恢复失败；Chat 停止；领域更新/删除、鉴权与网络错误。
- 覆盖率仅约束关键协议模块：`sse.ts` 门槛 statements/lines 95%、branches 85%、functions 100%；`chatStream.ts` 门槛 statements/lines 75%、branches 65%、functions 80%。实测合计 statements 97.19%、branches 82.05%、functions/lines 100%。
- 问题与解决：未对 1300 余行聚合 `api.ts` 设置会诱导低价值补测的全文件门槛，改为提取独立协议模块并设置可达的风险导向门槛；测试依赖未进入生产 dependencies 或 bundle。Vitest 排除 `e2e/**`，避免误加载 Playwright 规格导致 `npm test -- --run` 失败。
- 验证：`npm test -- --run` 为 5 files/25 tests passed；`npm run test:coverage` 通过；`npm run build` 通过；本项完成当时后端全量 pytest 通过（176 项；现行基线 `206`）。

回滚方案：

- 测试依赖与生产 bundle 分离；若框架升级阻塞，可固定版本，不删除已建立的测试。

### PLAN-410 浏览器 E2E

- **状态**：已完成（2026-07-16；2026-07-17 复验通过）
- **优先级**：P2
- **关联需求/功能**：REQ-001—REQ-006、REQ-010—REQ-014；FUN-001、FUN-004、FUN-062、FUN-080、FUN-100、FUN-125
- **目标**：用 Playwright 覆盖登录、默认/非默认 Agent 对话、计划确认、工具审批、任务取消、领域 CRUD 和深链导航。
- **依赖**：PLAN-120、PLAN-130、PLAN-200、PLAN-210、PLAN-300；PLAN-400。

执行步骤：

1. 建立可重复的 fake Provider/测试配置和隔离 workspace。
2. 编写登录与 API 鉴权、计划/审批、任务、领域和路由深链场景。
3. 每个场景独立准备和清理数据，失败保留 trace、截图和浏览器日志。
4. 将真实 Provider/渠道联调作为手工/受控环境套件，不放入默认 PR 门禁。

验收标准：

- 关键用户路径在 Chromium 上稳定通过，无固定 sleep。
- 失败产物可定位到 thread/trace/run。
- E2E 明确区分 fake 集成通过与真实第三方联通。

完成记录：

- 通过 npm 实际解析并锁定 `@playwright/test` `1.61.1`（当前 registry 最新；仅 `devDependencies`）；新增 `test:e2e`（默认 Chromium 门禁）与 `test:e2e:manual`（真实 Provider/渠道，不进默认门禁）。浏览器安装：`npx playwright install chromium`（见 `docs/TESTING.md`）。
- 默认套件使用 Playwright context 级 route fake Provider/后端（`frontend/e2e/fixtures/fakeBackend.ts`），每测例独立内存 store；E2E 启动 Vite 时设 `VITE_E2E_FAKE=1` 关闭 API 代理。可选 ASGI 脚本 `backend/scripts/e2e_fake_server.py` 提供隔离 `WORKSPACE_DIR` + FakeAgent。
- Chromium 项目 8 项覆盖：CONSOLE_PASSWORD 登录门、default/nondefault 对话与 `/plan` ExecutionRef 确认、工具审批批准、流式停止+服务端取消、任务深链取消、井/日报 CRUD 与 `well_id` 深链、设置/Agent 深链刷新。
- 失败保留 `trace`/`screenshot`/`video`，并附加 browser console 与 fake-backend 快照；无固定 `sleep`，改用 web-first 断言与可释放 hang stream。
- 验证（2026-07-17）：`npm run test:e2e` 8 passed（chromium）；`npm test -- --run` 25 passed；`npm run build` 通过；本项完成当时后端全量 pytest `176` 通过（现行基线见 PLAN-001/650：`206`）。PLAN-420 后续已完成。

回滚方案：

- 不稳定用例可临时 quarantine 并设责任人与修复期限，不能静默删除。

### PLAN-420 持续集成与发布门禁

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联需求/功能**：REQ-006、REQ-308、REQ-309；FUN-123、FUN-128—FUN-131
- **目标**：建立实际 CI workflow，而不是文档示例。
- **依赖**：PLAN-400；PLAN-410 可作为后续 job。

执行步骤：

1. 创建 CI：后端 pytest、Python lint/type、前端 test/build、Compose config。
2. 增加 OpenAPI 快照生成和非预期 breaking diff 检查。
3. 增加依赖/密钥/镜像扫描，固定 Python/npm 安装方式。
4. 缓存依赖但不缓存 workspace；上传失败日志、覆盖率和 E2E 产物。
5. 定义 required checks 与发布前真实集成验收清单。

完成记录：

- 落地 `.github/workflows/ci.yml`：jobs 为 `backend`（ruff/mypy/OpenAPI/pytest）、`frontend`（`npm test -- --run` / `test:coverage` / `build`）、`e2e`（Playwright chromium + `--with-deps`）、`compose`（`docker compose config --quiet`）、`security`（`pip-audit` + `npm audit --omit=dev --audit-level=high`）、可选 `gitleaks`（`continue-on-error: true`）。
- 缓存仅覆盖 pip/npm 依赖锁文件，不缓存业务 `workspace/`；失败上传 pytest junit、覆盖率、Playwright `test-results/` / `playwright-report/` 与审计文本。
- OpenAPI：`backend/scripts/export_openapi.py` 生成 `backend/openapi.snapshot.json`；`check_openapi_breaking.py` 仅对删除 operation、新增必填参数/body 字段、删除 2xx 状态码失败，忽略描述/示例等脆弱噪声。
- 本地复现：`scripts/ci-local.ps1` / `scripts/ci-local.sh`；开发依赖见 `backend/requirements-dev.txt` 与 `backend/pyproject.toml`。
- 真实 Provider/渠道仍仅 `npm run test:e2e:manual`，不进默认 CI。
- 验证（2026-07-17，本机等价命令）：ruff/mypy/OpenAPI/pytest/Vitest/coverage/build/E2E/compose 通过；**workflow 已落盘，云端 Actions 待仓库启用**（当前目录无 `.git`/remote 时无法触发 GitHub Actions）。

启用 required checks（仓库推到 GitHub 并打开 Actions 后）：

1. 合并至少一次使 `CI` workflow 在默认分支跑通。
2. Settings → Branches → Branch protection rule（如 `main`）→ Require status checks to pass before merging。
3. 勾选建议 required：`Backend (pytest / lint / type / OpenAPI)`、`Frontend (test / coverage / build)`、`Playwright E2E (chromium / fake Provider)`、`Docker Compose config`、`Security (pip-audit / npm audit)`。
4. 先观察后 required：`Gitleaks (optional)` 默认非阻断；镜像 CVE 扫描未做阻断门禁，可后续加 Trivy 等。
5. 误报时临时取消单个 check 的 required 并登记期限，不删除 workflow。

验收标准：

- push/PR 自动运行，失败阻止合并。
- CI 使用干净环境，不依赖开发机 `.venv`、`node_modules` 或业务 workspace。
- OpenAPI、后端、前端、Compose 的结果均可追溯。

回滚方案：

- 新门禁先观察后 required；误报时可临时降级为非阻断并登记期限，不删除检查。

## 8. 阶段 E：文档治理

### PLAN-500 文档持续治理

- **状态**：本轮闭环已完成（2026-07-17）；可持续再执行
- **优先级**：P1
- **关联需求/功能**：REQ-308；FUN-130
- **目标**：保持 REQ—FUN—API—PAGE—TEST—PLAN 可追溯，防止历史完成标记再次覆盖代码事实。
- **依赖**：所有计划项。

执行步骤：

1. API 变化先更新 schema/OpenAPI，再更新 `API.md` 人工索引。
2. 功能状态变化同步更新 `REQUIREMENTS.md`、`FEATURE_CATALOG.md`、`PROJECT_STATUS_REPORT.md` 和 `ACCEPTANCE_CHECKLIST.md`。
3. 测试数量和验证结果只在实际执行后更新 `TESTING.md`。
4. 完成计划项时在 `PROGRESS.md` 增加实现记录和证据；原始长记录继续只读归档。
5. 每次发布检查链接、编号、过期日期、敏感信息和“生产就绪”等过度表述。
6. CI 落地后加入 Markdown 链接、OpenAPI 索引和编号一致性检查。

验收标准：

- 每个部分/未完成验收项都映射到有效 PLAN 编号或明确标注“未排期”。
- API 人工文档与运行时 OpenAPI 无路径级漂移。
- 归档文档不再作为当前事实入口，现行导航无断链。

本轮完成记录（2026-07-17）：

- **实现思路**：在 PLAN-100—420 均已勾选的前提下，对现行 `docs/*.md`（排除 archive）与根 README 做全量审阅；统一最近验证基线；纠偏台账/矩阵中过期数字与“无前端测试/无 CI”等虚构或过期宣称；保持 RBAC、多实例、真实 Provider/渠道默认门禁等未排期项为未完成。
- **修改文件**：`DOCUMENT_INVENTORY.md`、`docs/README.md`、`PROJECT_STATUS_REPORT.md`、`IMPLEMENTATION_PLAN.md`、`PROGRESS.md`、`ACCEPTANCE_CHECKLIST.md`、`TESTING.md`、`REQUIREMENTS.md`、`FEATURE_CATALOG.md`、根 `README.md`；不改业务代码、不改 archive、不提交。
- **核心变更**：本项当时将最近基线统一为 pytest `176` / Vitest `25` / E2E `8` / build 通过 / CI workflow 落盘且云端待启用（现行基线见 PLAN-650：`206`）；ACCEPTANCE 中 PLAN-100—420 对应项按真实完成更新，并新增未排期项映射表；材料台账补齐 Vitest/E2E/CI/OpenAPI 快照与 `test_plan300_*`。
- **问题与解决**：`DOCUMENT_INVENTORY`/`TESTING` 矩阵与若干 DOC 记录仍写 166 或“无 CI”；`PROJECT_STATUS_REPORT` 领域节仍写“无 E2E”；根 README 仍写“部分实体缺完整 CRUD”。解决方式是以 2026-07-17 可重复命令与源码路由为准纠偏，历史“当时基线”保留语境但不覆盖现行结论。
- **验证**：相对链接抽检无断链；`--collect-only` 汇总 176；前端测试文件 5 + E2E 规格存在；`.github/workflows/ci.yml` 与 `scripts/ci-local.*` 存在且无 `.git`。后续契约或验证数字变化时按本清单再跑一轮。

回滚方案：

- 文档变更可独立回退；若代码与文档冲突，立即以代码/OpenAPI 修正文档，不回退代码来迎合旧文字。

## 9. 阶段 F：运维闭环补齐（PLAN-600+）

> 基线：2026-07-17。在 PLAN-100—500 完成后，将验收清单中明确的运维缺口升格为可执行计划；仍不纳入 RBAC、多实例、真实 Provider/渠道默认门禁等架构级未排期项。

| 阶段 | 计划 | 优先级 | 状态 | 主要依赖 |
|---|---|---:|---|---|
| 阶段 F：运维闭环 | PLAN-600—PLAN-640、PLAN-660—PLAN-710 | P1 | 已完成（2026-07-17） | PLAN-001 |
| 阶段 F：文档同步 | PLAN-650 | P1 | 已完成（2026-07-17） | PLAN-600—640 |

### PLAN-600 Cron 运行历史持久化

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联**：REQ-182；FUN-084、FUN-085
- **目标**：Cron 运行历史落盘并跨重启可查询；保持 job 配置既有 JSON 持久。
- **实现**：`workspace/.cache/cron_history.json`；上限 500；与 `cron_jobs.json` 分文件。
- **验收**：历史文件可读写；重启后 `/tasks/cron/history` 可见；截断上限仍生效；`test_plan600_cron_history.py` 通过。

### PLAN-610 Heartbeat 配置持久化

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联**：REQ-183；FUN-086
- **目标**：PUT `/tasks/heartbeat` 写入 `.env` 并热更新调度；重启后配置不回退。
- **实现**：`HeartbeatService.update()` 写 `HEARTBEAT_*` 到 `.env` 并 `_apply_schedule()`。
- **验收**：enabled/interval/prompt 持久；启停重调度；`test_plan610_heartbeat_persist.py` 通过。

### PLAN-620 渠道 webhook 验签

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联**：REQ-166、REQ-184；FUN-087
- **目标**：`_handle_webhook` 早期调用各平台验签；补齐飞书/QQ/Telegram；明确 API Token 与 webhook 豁免边界。
- **实现**：路由读 raw body 后调用 `verify_signature(headers, body)`；钉钉 HMAC-SHA256；飞书 `verification_token`；QQ Bearer/`X-Signature`；Telegram `X-Telegram-Bot-Api-Secret-Token`（`TELEGRAM_WEBHOOK_SECRET`）；`ApiSecurityMiddleware` 豁免 `/gateway/*/webhook`。
- **验收**：签名错误 401；未配置密钥时 `signature=skipped` 放行；`test_plan620_webhook_signature.py` 通过。不宣称真实平台联调。

### PLAN-630 插件扫描与删除

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联**：REQ-124、REQ-125；FUN-024、FUN-025
- **目标**：安装前/按需扫描（复用 SkillScanner）；DELETE 卸载并更新 ENABLED_PLUGINS。
- **实现**：`plugins.py` 复用 `skill_scanner`；`POST /install` 扫描门禁；`GET /{name}/scan-report`、`POST /scan`；`DELETE /{name}` 清目录并写 `.env`；前端 PluginsManager 展示扫描报告与删除确认。
- **验收**：扫描报告 API；危险模式拒绝安装；删除后目录与注册表/`ENABLED_PLUGINS` 一致；路径穿越拒绝；`test_plan630_plugin_scan_delete.py` 通过。

### PLAN-640 Agent 磁盘发现与删除清理

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联**：REQ-143、REQ-145；FUN-045—FUN-047、FUN-049
- **目标**：`list_agents` 扫描磁盘（跳过 tombstone）；删除支持显式 `purge` 清盘/checkpoint 选项，默认保留 tombstone 语义。
- **实现**：`MultiAgentManager.list_agents` 扫描 `agents_root` 子目录并懒加载元数据；`DELETE /agents/{id}?purge=` / body `purge`；`CheckpointProvider.purge` 关闭并删除该 Agent SQLite；前端 AgentsPage 二段确认（仅注销/彻底清除）。
- **验收**：冷启动列表可见磁盘 Agent；tombstone 不可见；purge 后目录与 checkpoint 清理且 resume 409；default 拒绝；`test_plan640_agent_disk_purge.py` 通过。

### PLAN-650 运维阶段文档同步

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **目标**：同步需求/功能/API/验收/测试基线；勾选 PLAN-600—650。
- **实现**：对现行 `docs/*.md`（排除 archive）与根 README 做运维验收同步；统一最近基线 pytest `206` / Vitest `25` / E2E `8`（沿用）/`npm run build`；纠偏 Cron history、Heartbeat、渠道路由验签、插件扫描删除、Agent 磁盘发现/purge 的过期「未排期/[~]」表述；保留真实 Provider/渠道联调、RBAC、多实例为未排期。
- **验收**：PLAN-600—650 在计划/进度中均为已完成；`ACCEPTANCE_CHECKLIST` 对应项有证据；入口文档基线数字一致；无业务代码与 archive 改动。

### PLAN-660 Agent 空闲逐出生命周期调度

- **状态**：已完成（2026-07-17）
- **优先级**：P1
- **关联**：REQ-145、REQ-304；FUN-049
- **目标**：将已有 `MultiAgentManager.evict_idle()` 接入应用生命周期，避免已加载 Workspace Agent 长期驻留内存。
- **实现**：新增 `AgentIdleEvictionService`，随 FastAPI lifespan 启动后台循环，按 `AGENT_IDLE_TTL_MINUTES` 推导 60—300 秒检查间隔并周期调用 `evict_idle()`；应用关闭时取消后台任务。
- **验收**：服务可单次触发逐出；后台任务启动幂等并可停止；`test_plan660_agent_idle_eviction.py` 通过。

### PLAN-670 会话历史删除闭环

- **状态**：已完成（2026-07-17）
- **优先级**：P2
- **关联**：REQ-104；FUN-006
- **目标**：补齐会话历史的本地删除能力，避免聊天侧栏只能恢复/导出而无法清理过期会话。
- **实现**：`SessionStore.delete_session()` 删除对应 thread JSON；新增 `DELETE /api/v1/agent/sessions/{thread_id}`；前端 ChatHistoryPanel 增加确认删除按钮，删除后刷新列表。
- **验收**：删除存在会话返回 `{deleted}` 并移除 JSON；重复删除返回 404；前端 API 发出 DELETE 请求；会话删除不清理 Trace、checkpoint 或 Agent 历史旁路数据。

### PLAN-680 产物删除闭环

- **状态**：已完成（2026-07-17）
- **优先级**：P2
- **关联**：REQ-205；FUN-109
- **目标**：补齐产物中心的本地删除能力，允许清理不再需要的 chart/code 生成物。
- **实现**：复用文件根目录约束新增 `DELETE /api/v1/files/artifacts/{kind}/{filename}`；删除 chart/code 文件并同步删除对应 sidecar metadata；前端产物详情页增加确认删除按钮，删除后刷新列表。
- **验收**：删除存在产物返回 `{deleted,kind}` 并移除文件和 metadata；重复删除返回 404；非法 kind/路径仍受既有校验；前端 API 发出编码后的 DELETE 请求。

### PLAN-690 产物 SHA256 校验和

- **状态**：已完成（2026-07-17）
- **优先级**：P2
- **关联**：REQ-205；FUN-109
- **目标**：为产物列表补充内容校验依据，便于下载或外部留档后核对文件未被篡改。
- **实现**：`list_artifacts` 对 chart/code 文件按块计算 SHA256 并返回 `sha256` 字段；前端 `ArtifactInfo` 增加 `sha256`，产物详情展示前 12 位摘要。
- **验收**：后端产物测试校验 SHA256 与文件内容一致；前端 API 测试确认字段透传；不引入集中存储或签名体系。

### PLAN-700 LAS 上传基础门禁

- **状态**：已完成（2026-07-17）
- **优先级**：P2
- **关联**：REQ-203；FUN-105
- **目标**：补齐 LAS 上传的基础安全限制，拒绝明显非 LAS 或过大的上传内容。
- **实现**：新增 `LAS_UPLOAD_MAX_BYTES` 配置；上传前校验 `.las` 扩展名、大小上限和 LAS `~Curve/~A` 段标记；拒绝请求不创建上传文件或 LAS 记录。
- **验收**：非 `.las` 返回 400；超限返回 413；无 LAS 段标记返回 400；三类失败均不落盘、不落库；合法上传仍可解析并沉淀曲线数据。

### PLAN-710 会话归档闭环

- **状态**：已完成（2026-07-17）
- **优先级**：P2
- **关联**：REQ-104；FUN-006
- **目标**：为会话历史补齐归档能力，默认列表隐藏已归档会话，支持取消归档与「仅显示已归档」视图。
- **实现**：`SessionStore` 写入 `archived`/`archived_at`；`list_sessions` 支持 `include_archived`/`archived_only`；新增 `POST .../archive` 与 `POST .../unarchive`；前端 ChatHistoryPanel 增加归档按钮与归档视图切换。
- **验收**：归档后默认列表不可见；`archived_only` 仅返回已归档；取消归档后重回默认列表；不存在会话返回 404；归档不清理 Trace/checkpoint；前端契约测试覆盖 POST 与 query。

## 10. 不在本轮落地范围

以下需求保持有效但不纳入当前阶段排期：REQ-020 多用户/RBAC/SSO、REQ-021 分布式队列与多实例、REQ-022 生产密钥库、REQ-023 WITSML/实时井场数据、REQ-024 原生移动端与更多渠道、REQ-224 集中式可观测后端、REQ-305 多实例一致性、TEST-EXT-001/002 真实 Provider/渠道默认门禁。

这些事项只有在完成独立架构决策后，才能新增 PLAN 编号；当前不得以“未来演进”暗示已经实现。

## 11. 全局完成定义

任一“待实施”计划只有同时满足以下条件才能改为完成：

1. 代码主路径与失败路径已实现；
2. 后端/前端相应自动化测试通过；
3. 运行时 OpenAPI 与 API 索引同步；
4. `ACCEPTANCE_CHECKLIST.md` 中对应条目有可复现证据；
5. 回滚或降级路径验证可用；
6. 未把 fake/mock 结果表述为真实 Provider、渠道或生产环境验收。
