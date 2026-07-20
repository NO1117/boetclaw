# BoetClaw 落地清单与实现记录

> 本文档跟踪 [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) 的实现进度。
> 每完成一项即勾选，并在「实现记录」区追加：实现思路 / 修改文件 / 核心变更 / 问题与解决。
> 图例：`[ ]` 待办 · `[~]` 进行中 · `[x]` 已完成

> **2026-07-14 功能审计口径修订**：Phase 0-13 代表“代码/API/首版控制台交付”进度；最新功能报告代表“产品页面与业务闭环”进度。审计确认当前为单页 React 控制台，没有独立客户端路由；后端 `/api/v1/*` 路由较完整，但任务、Agent、安全、Provider、技能、插件、MCP、渠道、产物、会话、钻井领域实体仍有页面级或业务闭环缺口。为保持记录自洽，本文新增 Phase 14-16 作为后续闭环任务。

---

## 一、落地清单（全量任务项）

### Phase 0 · 项目校准 ✅
- [x] 0.1 requirements.txt 增加测试/渠道依赖
- [x] 0.2 .env.example + config.py 扩展配置字段
- [x] 0.3 observability.py 扩展 EventType 枚举
- [x] 0.4 tests/ 骨架 + 冒烟测试

### Phase 1 · 核心基座 ✅
- [x] 1.1 ObservabilityMiddleware（链路追踪中间件）
- [x] 1.2 BoetClawAgentFactory（Agent 工厂）
- [x] 1.3 AgentManager 接入工厂（向后兼容）
- [x] 1.4 startup.py 两阶段启动编排
- [x] 1.5 main.py lifespan 改造 + health 就绪标志

### Phase 2 · Plan 门控 + HITL ✅
- [x] 2.1 BoetClawState（扩展 plan_phase）
- [x] 2.2 PlanGateMiddleware
- [x] 2.3 工厂支持注入 PlanGate + state_schema
- [x] 2.4 POST /agent/plan/confirm 恢复 API
- [x] 2.5 联调 interrupt→confirm（fake-agent 自动化往返测试覆盖，无需 LLM Key）
- [x] 2.6 /plan 前缀识别（chat 路由，在 invoke 内处理）

### Phase 3 · ToolGuard 安全层 ✅
- [x] 3.1 execution_level.py（级别/严重度枚举）
- [x] 3.2 security/models.py（GuardFinding/GuardResult）
- [x] 3.3 guardians/base.py
- [x] 3.4 三 Guardian（rule/file/shell）
- [x] 3.5 engine.py（ToolGuardEngine + 决策矩阵）
- [x] 3.6 approval.py（ApprovalService）
- [x] 3.7 tool_guard_mw.py（拦截中间件）
- [x] 3.8 工厂固定中间件顺序（Observability→PlanGate→ToolGuard）
- [x] 3.9 security API（config/approvals/resume）
- [x] 3.10 单测 guardians（9 项）

### Phase 4 · 技能体系双层 ✅
- [x] 4.1 models.py（SkillInfo/SkillConflictError）
- [x] 4.2 store.py（目录解析 + SKILL.md frontmatter 解析）
- [x] 4.3 scanner.py（密钥/危险代码扫描）
- [x] 4.4 pool_service.py（技能池 CRUD + 安装前扫描）
- [x] 4.5 workspace_service.py（工作区副本 + 启停状态）
- [x] 4.6 registry.py（resolve_effective_skills）
- [x] 4.7 skills API（list/install/enable/add-to-workspace/scan）
- [x] 4.8 内置技能扩展（las-parser、hse-compliance）
- [x] 4.9 单测（5 项）

### Phase 5 · 多智能体 Workspace ✅
- [x] 5.1 workspace.py（Workspace 隔离容器：skills/files/config）
- [x] 5.2 multi_agent_manager.py（懒加载 + 每 agent 锁 + 空闲驱逐）
- [x] 5.3 agent_context.py（4 级路由优先级）
- [x] 5.4 runtime.py（共享 invoke/confirm 逻辑）
- [x] 5.5 agents API（list/create/get/delete）
- [x] 5.6 chat 支持 agent_id 路由到工作区
- [x] 5.7 单测（4 项，含并发懒加载单构建）

### Phase 6 · Provider 抽象 + 本地模型 ✅
- [x] 6.1 base.py（ModelInfo/ProviderInfo/Provider ABC）
- [x] 6.2 manager.py（ProviderManager 单例 + model_string 解析）
- [x] 6.3 openai/anthropic/ollama provider（ChatOllama 读 OLLAMA_BASE_URL）
- [x] 6.4 capability_cache.py（落盘 workspace/.cache/capabilities.json）
- [x] 6.5 工厂 _resolve_model（provider 已配置则返回实例，否则回退字符串）
- [x] 6.6 providers API（list/models/check）
- [x] 6.7 单测（6 项，Ollama 连通性容错）
- [x] 6.8 Provider base_url 配置（OpenAI/Anthropic 兼容本地模型或代理服务）

### Phase 7 · 记忆与上下文策略 ✅
- [x] 7.1 context_policy.py（AUTOMATION_SKIP_SOURCES + should_persist_memory）
- [x] 7.2 store_backend.py（get_store / get_memory_files，file|store|none）
- [x] 7.3 invoke 透传 source（user|channel|cron|heartbeat），自动化跳过记忆
- [x] 7.4 SummarizationMiddleware 可开关（工厂 _build_summarization_mw）
- [x] 7.5 单测（7 项，含来源区分 + 摘要中间件构建 + 优雅降级）

### Phase 8 · 渠道网关抽象与扩展 ✅
- [x] 8.1 base.py（BaseChannel ABC + GatewayMessage/GatewayResponse + RenderStyle）
- [x] 8.2 renderer.py（MessageRenderer：markdown/plain/card + 截断）
- [x] 8.3 manager.py（ChannelManager：注册 + 每渠道 Queue(1000) + 消费者）
- [x] 8.4 channels/dingtalk|feishu|qq（从 router.py 迁移）
- [x] 8.5 channels/telegram（Bot API webhook）
- [x] 8.6 webhook 路由经 ChannelManager 入队 + 通用 /{platform}/webhook
- [x] 8.7 真实回发（钉钉 sessionWebhook / 飞书 tenant_token / QQ OneBot / TG sendMessage）
- [x] 8.8 单测（10 项，含 4 渠道解析 + 队列满丢弃 + 消费者处理）

### Phase 9 · 定时任务 + 心跳 ✅
- [x] 9.1 cron_service.py（AsyncIOScheduler + CronJob JSON 持久化）
- [x] 9.2 add_job/remove/list，触发 source=cron → 回发渠道
- [x] 9.3 heartbeat.py（按间隔用 HEARTBEAT_PROMPT 问 agent，source=heartbeat）
- [x] 9.4 生命周期：phase2 启动调度器，lifespan 关停
- [x] 9.5 API：GET/POST/DELETE /tasks/cron、GET/PUT /tasks/heartbeat
- [x] 9.6 单测（6 项，含来源=cron/heartbeat 不写记忆）

### Phase 10 · 插件系统 + 魔法命令 ✅
- [x] 10.1 architecture.py（PluginType/PluginManifest/PluginInfo）
- [x] 10.2 loader.py（扫描 plugins_ext/*/manifest.json + 动态 import + registry）
- [x] 10.3 __all__ 自动发现工具；未启用不注册（安全默认）
- [x] 10.4 commands/registry.py（/new /clear /stop /restart /help /plan）
- [x] 10.5 chat 前置解析：/ 命令命中直接执行（不进 LLM）
- [x] 10.6 API：GET /plugins、POST /plugins/reload、GET /commands
- [x] 10.7 单测（8 项，含安全默认 + /new 切换 thread）

### Phase 11 · 前端控制台扩展 ✅（首版交付；产品闭环待补）
- [x] 11.1 api.ts 扩展（agents/skills/providers/cron/security/plugins/commands + planConfirm）
- [x] 11.2 AgentSwitcher.tsx（顶栏切换/创建 Agent）
- [x] 11.3 PlanConfirm.tsx（interrupted → 展示 todos → 批准/拒绝）
- [x] 11.4 ApprovalCard.tsx（工具审批：findings 展示 + 批准/拒绝，5s 轮询）
- [x] 11.5 SkillsManager.tsx（池/工作区列表、启停开关、添加、扫描）
- [x] 11.6 ProviderSettings.tsx（provider/模型、连通性检测）
- [x] 11.7 CronManager.tsx（定时任务 CRUD + 心跳开关）+ PluginsManager.tsx
- [x] 11.8 追踪面板增强（按类别着色/标签：安全/规划/工具/子智能体/调度…）
- [x] 11.9 npm run build 通过（TS 严格模式，0 错误）
  - 备注：报告审计判定为“首版控制台可用”，但不是页面级完整闭环。缺路由深链、任务重跑/取消 UI、Agent 详情/删除、安全设置页、Provider 写配置、技能安装/编辑、插件启停、MCP 管理、渠道审计、产物中心和会话历史。

### Phase 12 · 可观测性强化 ✅
- [x] 12.1 otel.py（FastAPI OTel 注入 + span 关联 boetclaw.trace_id）
- [x] 12.2 LangSmith 可选（setup_env 已有 LANGCHAIN_TRACING_V2 逻辑）
- [x] 12.3 timeline.py + GET /monitor/trace/{trace_id}/timeline
- [x] 12.4 TraceStore JSONL 落盘（workspace/.cache/traces.jsonl，重启可恢复）
- [x] 12.5 单测（5 项：持久化/时间线/API/OTel 幂等）

### Phase 13 · 部署与文档 ✅
- [x] 13.1 Dockerfile（多阶段：frontend-build / backend-runtime / frontend-runtime）+ docker-compose.yml（backend+frontend+可选 ollama）
- [x] 13.2 scripts/install.ps1 / install.sh（venv + pip + .env 初始化 + npm install）
- [x] 13.3 README.md 更新（架构、快速开始、配置、API、渠道、文档索引）
- [x] 13.4 docs 补齐：ARCHITECTURE.md / API.md / CHANNELS.md / SECURITY.md / DEPLOYMENT.md
- [x] 13.5 冒烟验证：pytest、npm build、docker compose config
- [x] 13.6 启动环境保护（Python 3.11-3.13 检查 + 缺依赖友好提示）

### Phase 14 · 产品路由与管理闭环补强 ✅
- [x] 14.1 引入页面级路由：/chat、/tasks、/agents、/trace、/settings/*
- [x] 14.2 任务生命周期 UI：详情、状态筛选、重跑、取消、Trace 跳转
- [x] 14.3 Agent 工作区页：详情、删除、运行历史、文件/技能聚合
- [x] 14.4 安全设置页：Guard 配置、待审批、审批历史
- [x] 14.5 Provider 配置写入：API Key/base_url/default model
- [x] 14.6 会话历史：线程列表、恢复、搜索、导出、刷新持久化

### Phase 15 · 扩展治理与运维闭环 ✅
- [x] 15.1 技能治理：安装、详情、编辑、删除、扫描详情
- [x] 15.2 插件治理：启用/停用、安装、manifest 详情、错误隔离
- [x] 15.3 MCP 管理：server 状态、工具详情、reload 结果
- [x] 15.4 渠道运维：配置状态、队列深度、消息历史、失败重试、回发记录
- [x] 15.5 调度增强：Cron 编辑、启停、手动触发、运行历史

### Phase 16 · 钻井领域数据与产物中心 ✅
- [x] 16.1 领域模型落地：Well、WellboreSection、DailyReport、DrillingParam、LasFile
- [x] 16.2 领域页面：/wells、/wells/:wellId、/reports、/params、/las/import
- [x] 16.3 query_drilling_params 接入真实数据源，保留 mock fallback
- [x] 16.4 产物中心：图表/代码预览、下载、关联任务/Trace/井号
- [x] 16.5 LAS 导入、质量检查与曲线数据沉淀

### Phase 17 · 审计遗留闭环补强 ✅
- [x] 17.1 Agent 工作区运行历史与文件索引专用 API/UI
- [x] 17.2 Agent 产物与任务/Trace/井号自动写入侧车元数据

### Phase 18 · 端到端验收冒烟 ✅
- [x] 18.1 `docker compose up` 端到端冒烟与前端浏览器回归

### Phase 19 · 安全审计持久化补强 ✅
- [x] 19.1 审批历史 JSON 持久化与恢复

### Phase 20 · Provider 配置持久化补强 ✅
- [x] 20.1 Provider API Key/base_url/default model 写入 `backend/.env`

### Phase 21 · Plan 编辑与历史审计补强 ✅
- [x] 21.1 Plan 编辑确认与 JSON 历史审计

### Phase 22 · Trace 时间线详情增强 ✅
- [x] 22.1 `/trace/:traceId` 结构化时间线、耗时与事件间隔详情

### Phase 23 · API 鉴权与限流补强 ✅
- [x] 23.1 API Token 鉴权、内存限流与健康检查豁免

### Phase 24 · 任务持久化与恢复补强 ✅
- [x] 24.1 任务 JSON 持久化、状态恢复与 running 重启中断标记

### Phase 25 · 渠道访问白名单补强 ✅
- [x] 25.1 渠道 `allowed_users` 白名单、拒绝审计与管理 API

### Phase 26 · 渠道访问控制页面闭环 ✅
- [x] 26.1 `/settings/channels` 白名单编辑、保存与 denied 状态筛选

### Phase 27 · 插件启停持久化补强 ✅
- [x] 27.1 插件 `ENABLED_PLUGINS` 写入 `.env` 并可重启恢复

### Phase 28 · LAS 文件上传导入闭环 ✅
- [x] 28.1 `/las/import` 本地文件上传、解析质检与曲线沉淀

### Phase 29 · Prometheus Metrics 监控补强 ✅
- [x] 29.1 `/monitor/metrics` Prometheus 文本指标端点

### Phase 30 · Agent 产物关联筛选闭环 ✅
- [x] 30.1 产物 API 与 `/artifacts` 页面支持 `agent_id` 展示和过滤

### Phase 31 · Plan 确认失败恢复审计 ✅
- [x] 31.1 Plan 确认恢复异常写入历史记录，并保留原异常语义

### Phase 32 · Console 登录 JWT 闭环 ✅
- [x] 32.1 `CONSOLE_PASSWORD` 控制台登录、短期 JWT、localStorage/cookie 会话与退出

### Phase 33 · 技能 Reload 与 Agent 重建闭环 ✅
- [x] 33.1 `/skills/reload` 刷新已加载 Agent，使技能变更运行期生效

### Phase 34 · 渠道消息历史持久化闭环 ✅
- [x] 34.1 渠道消息历史写入 JSON，重启后可恢复查询

### Phase 35 · OpenTelemetry 控制台导出稳定性补强 ✅
- [x] 35.1 默认关闭 ConsoleSpanExporter，消除测试退出关闭流异常

### Phase 36 · 渠道用户级限流防刷 ✅
- [x] 36.1 `GATEWAY_RATE_LIMIT_PER_MINUTE` 按渠道用户限流并记录 `rate_limited` 审计

### Phase 37 · 审批 Pending 重启失效审计 ✅
- [x] 37.1 重启恢复时将不可恢复的 pending 审批标记为 `expired`

### Phase 38 · API Token 维度限流补强 ✅
- [x] 38.1 API 限流按 token 优先、IP 兜底分桶

### Phase 39 · Provider 模型解析限流补强 ✅
- [x] 39.1 `PROVIDER_RATE_LIMIT_PER_MINUTE` 按 provider/model 限制模型解析频率

---

## 二、当前功能闭环状态（按 2026-07-14 报告）

### 已完整接通
- [x] 智能对话主工作台：`/` 或 `/ui/`，API `/api/v1/agent/chat`、`/api/v1/agent/chat/stream`
- [x] 规划确认闭环：聊天页内嵌 `PlanConfirm`，API `/api/v1/agent/plan/confirm`
- [x] 钻井领域内置工具：`review_text`、`generate_text`、`generate_chart`、`generate_code`、`query_drilling_params`
- [x] 渠道网关后端：钉钉/飞书/QQ/Telegram Webhook 与任务回发链路
- [x] 根入口与静态 UI：`GET /`、`/ui/`
- [x] 页面级路由与深链：`/chat`、`/tasks/:taskId`、`/agents/:agentId`、`/trace/:traceId`、`/settings/*`
- [x] 任务生命周期 UI：状态筛选、详情、重跑、取消、Trace 跳转
- [x] 安全与 Provider 设置：Guard level、待审批、审批历史、Provider 配置写入、默认模型切换
- [x] 会话历史：线程列表、搜索、恢复、Markdown 导出、JSON 刷新持久化
- [x] 扩展治理：技能安装/详情/编辑/删除/扫描详情，插件安装/启停/manifest/错误隔离，MCP server/工具/reload 管理
- [x] 运维闭环：渠道状态/队列/消息历史/失败重试，Cron 编辑/启停/手动触发/运行历史
- [x] 钻井领域数据：井、井段、日报、参数、LAS 文件与曲线质量报告已落地
- [x] 领域页面与产物中心：`/wells`、`/reports`、`/params`、`/las/import`、`/artifacts`
- [x] 参数工具真实数据源：`query_drilling_params` 已接领域参数库并保留 mock fallback
- [x] 多智能体工作区：详情、删除、技能聚合、运行历史、文件索引均已接通
- [x] Agent 产物元数据自动关联：图表/代码生成后自动写入 task、trace、run、agent、well 侧车元数据
- [x] Docker 端到端验收：Compose 构建启动、后端健康、OpenAPI、前端入口与关键页面浏览器回归均通过
- [x] 安全审计持久化：审批历史已写入 `workspace/security/approval_history.json`，服务重启后可恢复
- [x] Provider 配置持久化：API Key、base_url 与默认模型写入 `backend/.env`，重启后可恢复
- [x] Plan 编辑与审计：计划可编辑提交，创建/确认历史写入 `workspace/plans/plan_history.json`
- [x] Trace 详情可观测性：`/trace/:traceId` 已展示结构化时间线、总耗时、事件间隔和分类统计
- [x] API 安全补强：`API_TOKEN` Bearer 鉴权、`API_RATE_LIMIT_PER_MINUTE` 限流与健康检查豁免已落地
- [x] 任务持久化：任务列表、状态、结果、Trace/run 和 metadata 已写入 `workspace/tasks/task_history.json`，服务重启后可恢复
- [x] 渠道访问控制：每渠道 `allowed_users` 白名单可查询/更新，非白名单消息拒绝并写入消息历史与 Trace 事件
- [x] 渠道访问控制页面：`/settings/channels` 可编辑保存白名单，并可筛选查看 `denied` 拒绝记录
- [x] 插件启停持久化：插件治理页/API 启停后同步更新 `ENABLED_PLUGINS` 到 `backend/.env`，重启后可恢复
- [x] LAS 上传导入：`/las/import` 支持本地 LAS 文件上传，后端保存、解析、质检并生成曲线 JSON
- [x] Metrics 监控端点：`/api/v1/monitor/metrics` 已输出 Prometheus 文本指标，覆盖任务、Trace、审批和网关队列
- [x] Agent 产物关联筛选：产物中心可显示来源 Agent，并按 `agent_id` 过滤图表/代码产物
- [x] Plan 失败恢复审计：确认恢复异常会写入 `workspace/plans/plan_history.json`，保留失败动作和错误摘要
- [x] Console 登录：配置 `CONSOLE_PASSWORD` 后启用密码登录，短期 JWT 保持会话，支持退出并兼容 API Token
- [x] 技能 Reload：`/api/v1/skills/reload` 可刷新已加载 Workspace Agent，让技能安装、编辑和启停在运行期生效
- [x] 渠道消息历史持久化：`/api/v1/gateway/messages` 的审计记录写入 `workspace/gateway/message_history.json`，服务重启后可恢复查询
- [x] OTel 导出稳定性：默认关闭控制台 span 导出，保留 FastAPI instrumentation 和 trace_id 关联，测试退出不再出现关闭流异常
- [x] 渠道用户级限流：`GATEWAY_RATE_LIMIT_PER_MINUTE` 可按 `platform:user_id` 限制消息频率，超限记录可审计
- [x] 审批 Pending 重启失效：重启前未处理审批恢复为 `expired` 历史，不再显示为可操作待审批
- [x] API Token 维度限流：`API_RATE_LIMIT_PER_MINUTE` 按 token 优先、IP 兜底分桶，避免同代理多 token 互相挤占限额
- [x] Provider 模型解析限流：`PROVIDER_RATE_LIMIT_PER_MINUTE` 可按 `provider:model` 限制模型解析频率
- [x] MCP Recover 指标：`/api/v1/monitor/metrics` 暴露 MCP reload/recover 成功与失败计数
- [x] Metrics 表核心计数：`/api/v1/monitor/metrics` 暴露 Agent 运行、工具调用、Guard 拦截和 Provider 重试/解析计数
- [x] Agent 运行耗时指标：`/api/v1/monitor/metrics` 暴露 `boetclaw_agent_run_duration_seconds` histogram
- [x] 命令文案 i18n：slash command 帮助与响应支持默认中文和请求级英文覆盖
- [x] i18n Header 覆盖：`/api/v1/agent/chat` 命令响应支持 `Accept-Language`，且 body `lang` 优先
- [x] 计划状态闭合审计：Phase 14-17 子项全完成后阶段标题同步为完成态
- [x] 安全提示 i18n：ToolGuard 安全拦截和拒绝执行文案支持中英文

## 三、实现记录（按完成时间倒序追加）

<!-- 每完成一项，在此区顶部追加记录条目 -->

### [Phase 46.1] 安全提示 i18n 闭环 — 已完成

**实现思路**：N.1 i18n 计划中除命令帮助外，还要求安全提示、审批文案抽到字典。当前 `ToolGuardMiddleware` 的安全拦截和用户拒绝执行消息仍为硬编码中文。本次在不改变 Guard 判定、审批创建和 interrupt 恢复语义的前提下，将这两类面向用户的安全文案接入 `app/i18n`；同时为 i18n helper 增加运行时语言 ContextVar，让 `/agent/chat` 解析出的 body/header 语言可以传递到 Agent 工具执行链路。

**修改文件**：
- 修改 `backend/app/i18n/__init__.py`：新增 `lang_var`、`set_lang()`、`reset_lang()`；`t()` 默认读取当前语言上下文；新增 `security.blocked`、`security.user_rejected` 中英文文案。
- 修改 `backend/app/api/routes/agent.py`：`/agent/chat` 在解析语言后设置 i18n 上下文，并在请求结束时恢复，覆盖命令和 Agent 工具执行链路。
- 修改 `backend/app/middleware/tool_guard_mw.py`：安全拦截和用户拒绝执行返回内容改为 `t()` 翻译。
- 修改 `backend/tests/test_phase3_security.py`：新增英文安全拦截和英文拒绝执行测试，保留默认中文兼容断言。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 46、M-AK、G40 与本实现记录。

**核心代码变更**：
- `normalize_lang()` 优先读取显式语言，其次读取 `lang_var`，最后回退配置 `settings.lang`。
- `/agent/chat` 使用 `set_lang(lang)` 设置当前请求语言，并在 `finally` 中 `reset_lang()`，避免跨请求污染。
- `ToolGuardMiddleware` 将 `[安全拦截] {reason}` 替换为 `t("security.blocked", reason=result.reason)`，将 `[用户拒绝执行]` 替换为 `t("security.user_rejected")`。

**遇到的问题与解决方案**：
- 问题：ToolGuard 运行在 Agent 工具调用中，不能直接读取 HTTP 请求体或 header。
  解决：使用 ContextVar 保存当前请求语言，`/agent/chat` 设置上下文后进入 Agent 执行，ToolGuard 通过 `t()` 自动读取。
- 问题：拒绝执行路径依赖 LangGraph `interrupt()`，单测环境默认会降级 approve。
  解决：测试中 monkeypatch `langgraph.types.interrupt` 返回 `reject`，稳定覆盖用户拒绝分支。
- 问题：需要保持默认中文行为兼容。
  解决：保留原有中文文本作为 `zh` 字典内容，并保留现有测试断言 `安全拦截`。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase3_security.py backend/tests/test_phase10_plugins.py` → 28 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 45.1] 计划状态闭合审计 — 已完成

**实现思路**：用户要求先检查计划，把还没完成但可以闭合的任务做完。通过扫描 `IMPLEMENTATION_PLAN.md` 和 `PROGRESS.md` 中的 `[ ]`、`[~]`、未完成、未实现、缺口等标记，确认当前全量任务项均已勾选；但 `PROGRESS.md` 中 Phase 14-17 的子项已经全部 `[x]`，阶段标题仍保留 `⏳`，属于进度状态漂移。本次先闭合该状态漂移，保证进度文档与实际子任务状态一致。

**修改文件**：
- 修改 `docs/PROGRESS.md`：将 Phase 14、Phase 15、Phase 16、Phase 17 的标题状态从 `⏳` 改为 `✅`；新增顶部清单项和本实现记录。
- 修改 `docs/IMPLEMENTATION_PLAN.md`：新增 Phase 45、M-AJ、G39，记录计划状态闭合审计已完成。

**核心代码变更**：
- 本阶段不涉及运行时代码变更，只修正计划和进度文档状态。
- Phase 14-17 标题状态现在与其所有已勾选子项保持一致。
- `IMPLEMENTATION_PLAN.md` 增加 Phase 45 的检查步骤、DoD、里程碑和总验收项，确保这次文档闭合也可追溯。

**遇到的问题与解决方案**：
- 问题：计划扫描没有发现未勾选的 `[ ]` 或 `[~]` 任务，但旧审计说明中仍包含“缺”“后续”等历史描述，容易和当前完成态混淆。
  解决：只把“子项已经全 `[x]` 但阶段标题仍为 `⏳`”作为本次可闭合任务处理；SQLite、RBAC、向量库等仍属于未来演进，不在本阶段冒进实现。
- 问题：文档状态修正没有代码测试可运行。
  解决：通过 `rg` 复查 Phase 14-17 标题、Phase 45、M-AJ、G39 和本记录是否同步，并用 `ReadLints` 确认无相关诊断。

**验证**：`rg` 复查 `docs/PROGRESS.md` 与 `docs/IMPLEMENTATION_PLAN.md` 中 Phase 14-17、Phase 45、M-AJ、G39 均已同步；`ReadLints` 检查文档无诊断。

### [Phase 44.1] i18n Header 覆盖补齐 — 已完成

**实现思路**：Phase 43 已完成命令文案 i18n 和 body `lang` 覆盖，但 N.1 的“请求级覆盖”在 HTTP 场景中还应支持 `Accept-Language`。本次沿用已新增的 `lang_from_headers()`，只在 `/agent/chat` 的 slash command 预解析路径接入 header 解析，语言优先级为 body `lang` > `Accept-Language` > 配置 `LANG`。普通 LLM 消息、`/plan` 透传和多 Agent 调用路径保持不变。

**修改文件**：
- 修改 `backend/app/api/routes/agent.py`：`chat()` 路由接收 FastAPI `Request`，调用 `lang_from_headers(request.headers, body.lang)`，并将解析后的语言传入命令上下文。
- 修改 `backend/tests/test_phase10_plugins.py`：新增 `Accept-Language: en-US,en;q=0.9` 覆盖测试，以及 body `lang=zh` 优先于英文 header 的测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 44、M-AI、G38 与本实现记录。

**核心代码变更**：
- `chat(request: Request, body: ChatRequest)` 将原 ChatRequest 参数改名为 `body`，避免与 FastAPI request 对象冲突。
- `lang_from_headers()` 处理区域语言和 q 参数，`en-US,en;q=0.9` 归一为 `en`。
- command 执行上下文传入解析后的 `lang`，因此 `/help`、`/new` 等命令可自动响应 header 语言。

**遇到的问题与解决方案**：
- 问题：FastAPI 路由原参数名为 `request: ChatRequest`，需要同时访问 HTTP header 与请求体。
  解决：将 HTTP request 命名为 `request`，将 Pydantic 请求体命名为 `body`，内部引用同步替换，避免语义混淆。
- 问题：header 和 body 同时存在时必须有确定优先级。
  解决：复用 `lang_from_headers(headers, explicit)` 的 explicit 优先策略，测试覆盖 body `lang=zh` 覆盖英文 header。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase10_plugins.py` → 14 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 43.1] 命令文案 i18n 轻量闭环 — 已完成

**实现思路**：N.1 i18n 计划要求支持 `zh/en` 两语言、请求级覆盖，并将命令帮助等文案抽到字典。为避免一次性改动安全、审批、前端和 Agent prompt，本次先完成最小可验证闭环：新增后端 `app/i18n` 字典和 `t()` helper，将 slash command 的帮助描述与控制命令响应接入翻译；`ChatRequest.lang` 作为请求级覆盖入口，`/agent/chat` 在命令预解析时透传语言上下文。

**修改文件**：
- 新增 `backend/app/i18n/__init__.py`：实现 `SUPPORTED_LANGS`、中英文消息字典、`normalize_lang()`、`t()`、`lang_from_headers()`。
- 修改 `backend/app/commands/registry.py`：内置命令描述改为翻译 key，`/help`、`/new`、`/clear`、`/stop`、`/restart` 根据上下文语言返回文案。
- 修改 `backend/app/api/schemas.py`：`ChatRequest` 增加可选 `lang` 字段。
- 修改 `backend/app/api/routes/agent.py`：`/agent/chat` 执行 slash command 时传入 `lang`。
- 修改 `backend/tests/test_phase10_plugins.py`：新增命令英文上下文和 chat API `lang=en` 覆盖测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 43、M-AH、G37 与本实现记录。

**核心代码变更**：
- `normalize_lang()` 支持 `en-US` 这类区域语言归一到 `en`，未知语言回退 `zh`。
- `CommandRegistry.list_commands(lang)` 动态翻译命令描述，默认仍使用配置语言。
- 控制命令 handler 从 `ctx["lang"]` 读取语言并调用 `t("commands.<name>.response", lang)`。
- `/agent/chat` 对 `/help` 等控制命令返回本地化响应，普通消息与 `/plan` 透传逻辑保持不变。

**遇到的问题与解决方案**：
- 问题：N.1 范围较宽，若同时修改安全提示、审批文案、Agent 系统提示和前端，容易形成大范围不可控改动。
  解决：先落地命令帮助与命令响应这个稳定文案闭环，并提供 `t()`/`normalize_lang()` 作为后续安全和审批文案复用基础。
- 问题：请求级覆盖既可以来自 header，也可以来自 body；现有 `ChatRequest` 没有语言字段。
  解决：先新增 `ChatRequest.lang`，避免重构 FastAPI 参数；i18n helper 预留 `lang_from_headers()` 供后续 API 中间件或路由扩展。
- 问题：内置命令描述原来直接存中文字符串。
  解决：仅内置命令使用 `commands.*.description` 翻译 key；若后续插件注册普通 description，仍按原字符串显示。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase10_plugins.py` → 12 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 42.1] Agent 运行耗时 Histogram — 已完成

**实现思路**：M.3 Metrics 表中还剩 `agent_run_duration_seconds` 未输出。现有运行链路已经发出 `AGENT_START` 与 `AGENT_END` 事件，并携带 `run_id` 与时间戳，因此本次不修改 Agent 执行流程，只在 metrics 端点按 `run_id` 配对 start/end，计算完成运行的端到端耗时，再生成 Prometheus histogram 文本。

**修改文件**：
- 修改 `backend/app/api/routes/monitor.py`：新增 `_agent_run_durations_seconds()` 与 `_histogram_lines()`，输出 `boetclaw_agent_run_duration_seconds_bucket/count/sum`。
- 修改 `backend/tests/test_phase12_observability.py`：metrics 测试用同一 `run_id` 构造 `AGENT_START`/`AGENT_END`，断言 histogram bucket/count/sum 输出。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 42、M-AG、G36 与本实现记录。

**核心代码变更**：
- `_agent_run_durations_seconds(events)` 解析事件 ISO 时间戳，记录每个 `run_id` 的 start 时间，并在遇到同 run 的 end 时计算秒级耗时。
- `_histogram_lines(name, values, buckets)` 生成 Prometheus histogram 的 `_bucket`、`_count`、`_sum` 行。
- `/monitor/metrics` 增加 `# TYPE boetclaw_agent_run_duration_seconds histogram` 及固定 bucket：`1/5/10/30/60/300/+Inf`。

**遇到的问题与解决方案**：
- 问题：历史事件中可能存在只有 start、只有 end、时间戳不可解析或顺序异常的记录。
  解决：指标聚合时跳过不可解析、缺少配对或负耗时事件，避免 metrics 端点因单条脏数据失败。
- 问题：测试如果不指定 `run_id`，`emit_event()` 会为 start/end 生成不同运行 ID，无法配对。
  解决：测试显式传入同一个 `run_id="metrics-run"`，保证 histogram 计数稳定为 1。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase12_observability.py` → 6 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 41.1] Metrics 表核心计数补齐 — 已完成

**实现思路**：计划 M.3 Metrics 表中除任务、Trace、审批、网关队列和 MCP recover 外，还列出了 Agent 运行、工具调用、Guard 拦截和 LLM/Provider 重试类指标。当前这些信息已经作为 `TraceStore` 事件存在，因此本次不改运行链路、不引入 `prometheus-client`，只在 `/api/v1/monitor/metrics` 中基于内存事件聚合 Prometheus 文本 Counter。

**修改文件**：
- 修改 `backend/app/api/routes/monitor.py`：新增事件聚合辅助函数，输出 `boetclaw_agent_runs_total`、`boetclaw_tool_calls_total`、`boetclaw_guard_blocks_total`、`boetclaw_llm_retries_total`。
- 修改 `backend/tests/test_phase12_observability.py`：扩展 metrics 测试，隔离 `trace_store._events` 后构造 Agent、Tool、Guard、Provider 事件并断言输出。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 41、M-AF、G35 与本实现记录。

**核心代码变更**：
- `_count_by_label()` 按事件类型和数据字段聚合标签计数，用于 Guard 与 Provider 维度。
- `_tool_call_counts()` 将 `TOOL_CALL` 计为 `started`，将 `TOOL_RESULT` 计为 `completed`。
- `metrics()` 将 `AGENT_START`、`AGENT_END`、`ERROR` 聚合为 `started`、`completed`、`failed` 状态，并追加对应 Prometheus HELP/TYPE/metric 行。
- 保留既有任务、Trace、审批、网关队列和 MCP recover 指标输出。

**遇到的问题与解决方案**：
- 问题：当前事件里没有独立的 Agent failed 事件，只有通用 `ERROR`。
  解决：先将 `ERROR` 作为 `boetclaw_agent_runs_total{status="failed"}` 的轻量近似口径；后续如果引入专门的运行结果事件，可替换为更精确统计。
- 问题：Guard 事件数据当前多记录 `tool/reason`，不一定有 `guardian` 字段。
  解决：聚合时优先读取 `guardian`，缺失则归入 `tool_guard`，避免丢失拦截计数。
- 问题：TraceStore 是全局单例，metrics 测试容易被其它测试产生的事件污染。
  解决：测试中 monkeypatch `trace_store._events=[]` 后再构造事件，确保断言稳定。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase12_observability.py` → 6 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 40.1] MCP Recover 指标闭环 — 已完成

**实现思路**：计划 Metrics 章节列出了 `mcp_recover_total{result}`，但当前 `/monitor/metrics` 只覆盖任务、Trace、审批和网关队列，MCP reload/recover 是否成功缺少可抓取指标。本次不引入新的 metrics 依赖，沿用现有 Prometheus 文本输出方式：在 `MCPManager.reload()` 统一入口记录 `success`/`failed` 计数并发出 `MCP_RECOVER` 事件，再由 `/api/v1/monitor/metrics` 输出 `boetclaw_mcp_recover_total{result=...}`。

**修改文件**：
- 修改 `backend/app/tools/mcp_manager.py`：新增 `_recover_counts`、`recover_counts()`，并在 `reload()` 成功/失败时更新计数和发事件。
- 修改 `backend/app/api/routes/monitor.py`：在 Prometheus 文本中输出 `boetclaw_mcp_recover_total`。
- 修改 `backend/tests/test_phase12_observability.py`：扩展 metrics 测试，断言 MCP recover 成败指标存在。
- 修改 `backend/tests/test_phase15_mcp.py`：新增 MCP reload 成功/失败计数测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 40、M-AE、G34 与本实现记录。

**核心代码变更**：
- `MCPManager.__init__()` 初始化 `{"success": 0, "failed": 0}` 计数器。
- `connect()` 返回布尔连接结果，保留原有 MCP 失败不打断服务的容错行为。
- `reload()` 成功完成 `disconnect()` + `connect()` 后按布尔结果递增 `success` 或 `failed` 并发出 `EventType.MCP_RECOVER`。
- `reload()` 遇到未捕获异常时递增 `failed`、记录错误事件并重新抛出异常，保持调用方可感知异常失败。
- `/monitor/metrics` 遍历 `mcp_manager.recover_counts()` 输出 `boetclaw_mcp_recover_total{result="success|failed"}`。

**遇到的问题与解决方案**：
- 问题：`connect()` 内部会吞掉部分连接异常并只记录错误事件，如果 `reload()` 只捕获异常会把真实连接失败误计为成功。
  解决：让 `connect()` 返回布尔连接结果，`reload()` 根据返回值计数；同时保留现有容错语义，避免改变启动和 MCP 管理 API 行为。
- 问题：Metrics 端点测试不能依赖真实 MCP reload，否则需要外部 MCP server。
  解决：metrics 测试直接设置 `_recover_counts`；管理器行为测试用 monkeypatch 替换 `disconnect/connect`，覆盖成功和异常路径。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase12_observability.py backend/tests/test_phase15_mcp.py` → 8 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 39.1] Provider 模型解析限流补强 — 已完成

**实现思路**：计划 Part N.2 中 Provider 级限流仍未落地。直接包裹 LangChain 模型对象的 `invoke/ainvoke/stream` 风险较高，可能影响 DeepAgents 对 Runnable 的类型和能力探测。因此本次采用低风险入口限流：在 `ProviderManager.get_chat_model()` 这个统一模型解析入口前增加 provider/model 维度的 60 秒滑动窗口。默认 `PROVIDER_RATE_LIMIT_PER_MINUTE=0` 关闭，开启后可限制频繁重建或解析同一 provider/model 的模型实例。

**修改文件**：
- 修改 `backend/app/core/config.py`：新增 `provider_rate_limit_per_minute`。
- 修改 `backend/.env.example`：新增 `PROVIDER_RATE_LIMIT_PER_MINUTE=0`。
- 新增 `backend/app/providers/rate_limiter.py`：实现 `ProviderRateLimiter` 和 `ProviderRateLimitError`。
- 修改 `backend/app/providers/manager.py`：`get_chat_model()` 创建具体模型前执行限流检查。
- 修改 `backend/tests/test_phase6_providers.py`：新增 Provider 限流器默认关闭、同 key 超限和不同 key 分桶测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 39、M-AD、G33 与本实现记录。

**核心代码变更**：
- `ProviderRateLimiter.check(provider, model)` 读取 `settings.provider_rate_limit_per_minute`；小于等于 0 时直接放行。
- 限流 key 为 `provider:model`，每个 key 维护一个 60 秒窗口内的命中队列。
- 超限时抛出 `ProviderRateLimitError("Provider rate limit exceeded for <key>")`。
- `ProviderManager.get_chat_model()` 在 `provider.get_chat_model()` 前调用 `provider_rate_limiter.check(provider_name, model)`。

**遇到的问题与解决方案**：
- 问题：要完整限制每次 LLM 调用，需要包装 LangChain 模型运行方法，可能破坏 DeepAgents/Runnable 兼容性。
  解决：先在稳定的统一模型解析入口实现轻量限流；后续若要限制每次 `invoke/ainvoke`，再单独设计模型 wrapper。
- 问题：测试不能构造真实模型，否则依赖外部 API 包和凭据。
  解决：直接测试 `ProviderRateLimiter`，并保留既有 provider 配置与持久化测试覆盖 `ProviderManager` 周边行为。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase6_providers.py` → 12 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 38.1] API Token 维度限流补强 — 已完成

**实现思路**：计划 Part N.2 对 API 限流的口径是“按 token/IP”，但 Phase 23 初始实现只按客户端 IP 做滑动窗口计数。在反向代理、公司网关或多人共享出口 IP 的部署中，不同 API Token 或 Console 会话会互相挤占限额。本次将限流 key 改为 token 优先：如果请求带 Bearer、`X-API-Token` 或 Console cookie token，则使用 token 的 SHA256 摘要作为分桶；没有 token 时继续按 IP 限流，保持零配置本地开发兼容。

**修改文件**：
- 修改 `backend/app/middleware/api_security_mw.py`：新增 `_rate_key()`，限流使用 token 摘要或 IP 作为 key。
- 修改 `backend/app/security/console_auth.py`：Console JWT payload 增加 `jti`，确保不同登录会话 token 不重复。
- 修改 `backend/tests/test_phase23_api_security.py`：新增不同 token 独立限流分桶测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 38、M-AC、G32 与本实现记录。

**核心代码变更**：
- `_rate_key()` 从 `Authorization: Bearer ...`、`X-API-Token` 或 `boetclaw_console_token` cookie 中提取 token；命中后返回 `token:<sha256前16位>`。
- 无 token 时返回 `ip:<client.host>`，沿用原本 IP 兜底行为。
- `create_console_token()` 增加 `jti=uuid4().hex`，避免同一秒内多次登录生成完全相同 token。

**遇到的问题与解决方案**：
- 问题：不能把明文 API Token 或 Console JWT 直接存进中间件 `_hits` key。
  解决：使用 SHA256 摘要前缀作为内存 key，只保留不可逆短摘要。
- 问题：测试两个 Console 登录会话时，同一秒内 token 可能相同，无法验证独立分桶。
  解决：JWT payload 增加 `jti`，每次登录生成唯一 token。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase23_api_security.py` → 5 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 37.1] 审批 Pending 重启失效审计 — 已完成

**实现思路**：安全审批历史已经写入 `workspace/security/approval_history.json`，但当前图 checkpoint 仍是 `MemorySaver`。如果服务在工具审批 pending 时重启，持久化文件能恢复审批记录，却无法恢复原 LangGraph interrupt 上下文；继续把这类记录放在 `/security/approvals` 待审批列表会误导用户点击批准/拒绝。此次在 `ApprovalService._load()` 中处理恢复边界：加载历史时将 `pending` 状态改为 `expired` 并回写文件；`expired` 不进入待审批列表，但保留在历史接口中用于审计。

**修改文件**：
- 修改 `backend/app/security/approval.py`：扩展状态注释为 `pending|approved|rejected|expired`；加载历史时将 pending 标记为 expired 并保存。
- 修改 `backend/tests/test_phase3_security.py`：新增 pending 审批重启失效测试；同时将旧的审批历史测试改为使用临时文件，避免读写真实 workspace 历史。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 37、M-AB、G31 与本实现记录。

**核心代码变更**：
- `_load()` 中读取每条 `ApprovalRequest` 后，如果 `req.status == "pending"`，则设置为 `expired`，并在加载完成后 `_save()` 回写。
- `list_pending()` 逻辑不变，只返回 `status == "pending"`，因此 expired 自动从待审批列表消失。
- `/security/approvals/history` 继续通过 `list_all()` 返回所有状态，expired 可在安全历史中追溯。

**遇到的问题与解决方案**：
- 问题：重启后 pending 审批缺少原 graph interrupt/checkpoint，上层无法安全恢复执行。
  解决：不伪造可恢复状态，恢复时转为 expired 历史，让用户看到曾有未处理审批但不能继续操作。
- 问题：新增测试时发现旧测试使用默认 workspace 持久化路径，会读到历史运行残留，导致断言数量不稳定。
  解决：将旧测试也切换为 `tmp_path / "security" / "approval_history.json"`，保证测试隔离。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase3_security.py` → 12 passed；`ReadLints` 检查相关文件无诊断。

### [Phase 36.1] 渠道用户级限流防刷 — 已完成

**实现思路**：计划 Part N.2 明确要求“渠道级每 user 每分钟消息上限，防刷”。此前已完成 API 级限流，但外部渠道 webhook 仍可被同一用户高频刷入队列。此次采用默认关闭的轻量内存限流：新增 `GATEWAY_RATE_LIMIT_PER_MINUTE`，当配置大于 0 时，`ChannelManager` 按 `platform:user_id` 维护 60 秒滑动窗口；超限消息不进入队列，并写入 `rate_limited` 审计记录。由于 webhook 原本在 `enqueue()` 返回 false 时会走 fallback 后台任务，本次在路由层提前识别超限并直接返回，避免超限消息被 fallback 继续执行。

**修改文件**：
- 修改 `backend/app/core/config.py`：新增 `gateway_rate_limit_per_minute`。
- 修改 `backend/.env.example`：新增 `GATEWAY_RATE_LIMIT_PER_MINUTE=0`。
- 修改 `backend/app/services/gateway/manager.py`：新增 `_rate_hits`、限流窗口检查、`record_rate_limited()`，并在 `enqueue()` 内保护内部入队路径。
- 修改 `backend/app/api/routes/gateway.py`：webhook 入队前识别超限并返回 `Rate limited`。
- 修改 `backend/tests/test_phase25_gateway_access_control.py`：新增 webhook 用户级限流测试。
- 修改 `backend/tests/test_phase15_gateway_ops.py`：新增直接 `enqueue()` 限流测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 36、M-AA、G30 与本实现记录。

**核心代码变更**：
- `_rate_limited(name, message, consume)` 按 `settings.gateway_rate_limit_per_minute` 清理 60 秒窗口内旧命中并判断是否超限。
- `is_rate_limited()` 只检查不消费计数，供 webhook 路由提前阻断 fallback。
- `consume_rate_limit()` 在 `enqueue()` 中消费计数，覆盖非 webhook 的内部直接入队路径。
- `record_rate_limited()` 发出 `GATEWAY_MESSAGE` 事件并写入消息历史 `status=rate_limited/detail=user_rate_limit`。

**遇到的问题与解决方案**：
- 问题：`enqueue()` 返回 false 原本会触发 webhook fallback，如果只在 `enqueue()` 内限流，超限消息仍可能被后台任务处理。
  解决：路由层先调用 `is_rate_limited()`，超限时直接记录并返回 `Rate limited`，不进入 fallback 分支；`enqueue()` 内仍保留限流作为内部调用保护。
- 问题：测试需要隔离全局 `channel_manager` 的限流窗口和历史文件。
  解决：测试中 monkeypatch `_rate_hits`、`_history`、`history_path`、channels/queues，并使用临时目录。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase15_gateway_ops.py backend/tests/test_phase25_gateway_access_control.py` → 7 passed；`ReadLints` 检查相关文件无诊断；命令输出无 OTel 关闭流异常。

### [Phase 35.1] OpenTelemetry 控制台导出稳定性补强 — 已完成

**实现思路**：多个后端测试阶段结束时都会出现 OpenTelemetry `ValueError: I/O operation on closed file`，pytest 退出码为 0 但日志噪声持续存在。检查发现 `setup_otel()` 默认注册了 `BatchSpanProcessor(ConsoleSpanExporter())`，测试进程退出时后台导出线程仍可能向已关闭的 stdout/stderr 写入。此次保留 OTel FastAPI instrumentation、`X-Trace-Id` 响应头和 `boetclaw.trace_id` span attribute，只把控制台 span 导出改为显式配置项，默认关闭。

**修改文件**：
- 修改 `backend/app/core/config.py`：新增 `otel_console_exporter: bool = False`。
- 修改 `backend/app/core/otel.py`：仅在 `settings.otel_console_exporter` 为 true 时注册 `ConsoleSpanExporter`。
- 修改 `backend/.env.example`：新增 `OTEL_CONSOLE_EXPORTER=false`。
- 修改 `backend/tests/test_phase12_observability.py`：补默认关闭控制台 exporter 的回归断言。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 35、M-Z、G29 与本实现记录。

**核心代码变更**：
- `setup_otel()` 仍在 `settings.otel_enabled` 为 true 时创建 `TracerProvider` 并执行 `FastAPIInstrumentor.instrument_app()`。
- `BatchSpanProcessor(ConsoleSpanExporter())` 延迟导入并受 `OTEL_CONSOLE_EXPORTER=true` 控制，默认不挂后台控制台导出线程。
- 原有 `_instrumented` 和 `_middleware_registered` 幂等保护不变。

**遇到的问题与解决方案**：
- 问题：直接关闭 `OTEL_ENABLED` 会丢失 HTTP instrumentation 和 trace_id 关联。
  解决：新增更细粒度的 `OTEL_CONSOLE_EXPORTER`，只关闭控制台导出，不关闭 OTel 注入。
- 问题：测试需要验证警告消失，但不应依赖 OpenTelemetry 私有 provider 结构。
  解决：在配置层断言默认 exporter 为 false，并运行此前会触发退出警告的测试组合，确认输出不再出现关闭流异常。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase12_observability.py backend/tests/test_phase15_gateway_ops.py` → 8 passed；`ReadLints` 检查相关文件无诊断；命令输出不再出现 `ValueError: I/O operation on closed file`。

### [Phase 34.1] 渠道消息历史持久化闭环 — 已完成

**实现思路**：Phase 15.4 已补齐渠道状态、队列深度、消息历史和失败重试，但消息历史只存在于 `ChannelManager._history` 内存中，服务重启后入队、失败、拒绝和回发记录都会丢失。本次沿用项目现有 JSON 持久化风格，在 `ChannelManager` 初始化时读取 `workspace/gateway/message_history.json`，每次 `record_message()` 后同步保存最近 500 条。运行期记录仍保留 `_message` 供失败重试使用，落盘时剔除该不可序列化对象；重启恢复后的旧记录只用于审计查询，不伪造重试上下文。

**修改文件**：
- 修改 `backend/app/services/gateway/manager.py`：新增 `history_path`、`_load_history()`、`_save_history()`、`_public_record()`，记录消息后自动保存。
- 修改 `backend/tests/test_phase15_gateway_ops.py`：现有 API 测试使用临时历史文件，并新增持久化恢复测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 34、M-Y、G28 与本实现记录。

**核心代码变更**：
- `ChannelManager.__init__()` 默认使用 `settings.workspace_dir / "gateway" / "message_history.json"` 作为消息历史文件。
- `record_message()` 仍把新记录插入内存头部并裁剪为最近 500 条，随后调用 `_save_history()` 写入 JSON。
- `_save_history()` 对每条记录调用 `_public_record()`，避免 `_message: GatewayMessage` 进入 JSON。
- `message_history()` 继续复用原过滤逻辑，返回字段结构与前端/API 兼容。

**遇到的问题与解决方案**：
- 问题：`GatewayMessage` 对象不可 JSON 序列化，但运行期失败重试依赖它。
  解决：内存记录保留 `_message`，持久化记录剔除 `_message`；重启后的旧记录仍可审计查询，但 `retry_message()` 返回 `False`，不尝试用不完整上下文重发。
- 问题：测试直接使用全局 `channel_manager` 可能污染真实 workspace 历史文件。
  解决：测试中将 `history_path` monkeypatch 到 `tmp_path`，独立持久化测试则新建 `ChannelManager(history_path=...)`。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase15_gateway_ops.py` → 2 passed；`ReadLints` 检查相关文件无诊断。测试结束仍观察到既有 OpenTelemetry `I/O operation on closed file` 非阻断警告，pytest 退出码为 0。

### [Phase 33.1] 技能 Reload 与 Agent 重建闭环 — 已完成

**实现思路**：计划 Step 4.9 和 API 表一直保留 `POST /api/v1/skills/reload`，用于技能变更后重建对应 Workspace Agent，但此前没有路由实现。现有 MultiAgent 采用懒加载，技能解析发生在 `_build_agent()` 阶段，因此 reload 的最小正确语义是：对已加载 Agent 在同一 agent lock 下清空并重建，使其重新读取最新技能目录；对未加载 Agent 不强制构建，保持下次访问时自然加载最新技能。

**修改文件**：
- 修改 `backend/app/agents/multi_agent_manager.py`：新增 `reload_agent()` 与 `reload_loaded_agents()`。
- 修改 `backend/app/api/routes/skills.py`：新增 `ReloadSkillsRequest` 和 `POST /skills/reload`。
- 修改 `backend/tests/test_phase4_skills.py`：新增 reload API 回归测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 33、M-X、G27 与本实现记录，并修正 `/skills/reload` 旧的“未实现”备注。

**核心代码变更**：
- `reload_agent(agent_id)` 使用现有 `_lock(agent_id)` 保证同一 Agent 不会边重建边被并发访问；已加载时调用 `_build_agent()` 重建并更新 `last_access`。
- `reload_loaded_agents()` 只遍历 `ws.agent is not None` 的工作区，避免全量构建未使用 Agent。
- `/api/v1/skills/reload` 支持 `{agent_id}` 精确刷新；未传时刷新所有当前已加载 Agent，返回 `{reloaded, agents}`。

**遇到的问题与解决方案**：
- 问题：技能变更后如果立即构建所有 Agent，可能触发大量 LLM/工具初始化，影响本地控制台响应。
  解决：仅重建已加载 Agent；未加载 Agent 保持懒加载语义，下次访问时自然读取最新技能配置。
- 问题：测试不能依赖真实 DeepAgents 构建，否则需要模型和外部依赖。
  解决：测试中 monkeypatch `multi_agent_manager._build_agent()` 返回轻量对象，验证 API 调用确实触发已加载 Agent 重建。
- 问题：测试修改全局 `multi_agent_manager` 状态可能污染后续用例。
  解决：测试前保存 `_ws/_locks/_root`，finally 中恢复。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase4_skills.py` → 7 passed；`ReadLints` 检查相关文件无诊断。测试结束仍观察到既有 OpenTelemetry `I/O operation on closed file` 非阻断警告，pytest 退出码为 0。

### [Phase 32.1] Console 登录 JWT 闭环 — 已完成

**实现思路**：计划 I.3 将 Console 登录列为可选增强。现有 API Token 适合脚本/API 调用，但前端控制台缺少用户可操作的登录入口。本次采用单用户本地部署的最小闭环：当 `CONSOLE_PASSWORD` 为空时保持原有开放体验；当其非空时，`/api/v1/auth/login` 校验密码并签发短期 HMAC JWT，前端将 token 存入 `localStorage`，后端同时写入 HttpOnly cookie；`ApiSecurityMiddleware` 接受原 API Token、`X-API-Token`、Console Bearer token 或 cookie。多用户 RBAC 不在本期实现。

**修改文件**：
- 新增 `backend/app/security/console_auth.py`：无外部依赖的 HMAC-SHA256 JWT 创建、校验和 Bearer 提取工具。
- 新增 `backend/app/api/routes/auth.py`：`/auth/status`、`/auth/login`、`/auth/logout`。
- 修改 `backend/app/core/config.py`、`backend/.env.example`：新增 `CONSOLE_PASSWORD`、`CONSOLE_JWT_SECRET`、`CONSOLE_JWT_TTL_MINUTES`。
- 修改 `backend/app/middleware/api_security_mw.py`：鉴权逻辑兼容 Console JWT，并豁免 auth 路由。
- 修改 `backend/app/main.py`：注册 auth 路由。
- 修改 `backend/tests/test_phase23_api_security.py`：补 Console 登录鉴权回归。
- 修改 `frontend/src/services/api.ts`：新增 Console auth 状态、登录、退出 API 封装与 localStorage token 存储。
- 修改 `frontend/src/App.tsx`、`frontend/src/App.css`：新增登录状态检查、登录页、退出按钮和样式。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 32、M-W、G26 与本实现记录。

**核心代码变更**：
- `create_console_token()` 生成带 `sub/iat/exp/scope` 的 JWT，签名算法为 HMAC-SHA256。
- `verify_console_token()` 校验签名、`scope=console` 和过期时间；`CONSOLE_PASSWORD` 未配置时不会接受 Console token。
- `ApiSecurityMiddleware._authorized()` 的判定顺序为：未启用任何鉴权则放行；API Bearer token；`X-API-Token`；Console Bearer/cookie token。
- 前端 `App` 启动调用 `fetchConsoleAuthStatus()`；需要登录且未认证时渲染 `LoginPage`；登录成功后回到控制台，退出时清除 cookie 和 localStorage。

**遇到的问题与解决方案**：
- 问题：前端已有大量直接 `fetch()` 调用，逐个改为带 Authorization header 风险大。
  解决：登录接口同时写入 HttpOnly cookie，生产同源部署下现有请求自动携带 cookie；localStorage token 仍保留，供状态接口和后续跨域/代理场景扩展。
- 问题：不能破坏已有 `API_TOKEN` 脚本调用方式。
  解决：中间件保留 Bearer API Token 与 `X-API-Token` 判定，Console JWT 只是新增可选凭据。
- 问题：不希望为单用户本地登录引入 PyJWT 依赖。
  解决：使用标准库 `hmac/hashlib/base64/json` 实现最小 JWT 创建与校验，并用测试覆盖错误密码、登录、Bearer、cookie 和登出。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase23_api_security.py` → 4 passed；`npm run build` → 通过；`ReadLints` 检查相关后端/前端文件无诊断。

### [Phase 31.1] Plan 确认失败恢复审计 — 已完成

**实现思路**：既有 Phase 21 已记录 Plan 创建、批准、拒绝和编辑，但 `confirm_plan()` 在 `Command(resume=...)` 恢复图失败时会直接抛异常，历史文件没有失败线索。本次在恢复调用外层增加异常审计：捕获异常后写入 `workspace/plans/plan_history.json`，action 采用 `<decision>_failed`，response 保存错误摘要，然后重新抛出原异常，避免改变 API 的失败语义。

**修改文件**：
- 修改 `backend/app/core/agent.py`：`confirm_plan()` 增加恢复异常记录。
- 修改 `backend/tests/test_phase2_plan.py`：新增失败恢复历史测试。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 31、M-V、G25 与本实现记录。

**核心代码变更**：
- `confirm_plan()` 对 `self.agent.ainvoke(Command(resume=resume_value), config=config)` 包裹 `try/except`。
- 异常路径调用 `plan_history_store.record(thread_id=..., action=f"{decision}_failed", edited_todos=..., response=str(exc))`。
- 记录完成后 `raise` 原异常，保持调用方仍能得到真实恢复失败。

**遇到的问题与解决方案**：
- 问题：失败路径如果直接返回成功结构，会掩盖 checkpoint 丢失或图恢复异常。
  解决：仅补审计记录，不吞异常、不改成功响应结构。
- 问题：需要验证历史写入与异常抛出同时成立。
  解决：新增 `FailingPlanAgent` 测试桩，让 `ainvoke()` 抛 `RuntimeError("checkpoint missing")`，断言历史 action 为 `approve_failed` 且错误摘要存在。

**验证**：`.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase2_plan.py` → 7 passed；`ReadLints` 检查 `agent.py` 与 `test_phase2_plan.py` 无诊断。

### [Phase 30.1] Agent 产物关联展示与筛选 — 已完成

**实现思路**：Phase 17.2 已让图表/代码生成工具自动写入包含 `agent_id` 的侧车元数据，但产物中心 API 只返回 `task_id`、`trace_id`、`well_id`，页面也无法按 Agent 查看生成物。本次沿用现有侧车元数据读取逻辑，在 `/files/artifacts` 返回 `agent_id` 并增加 `agent_id` 查询过滤；前端 `/artifacts` 页面增加 Agent ID 输入框，列表和详情展示来源 Agent。这样 Agent 工作区、任务历史和产物中心的关联链路闭合。

**修改文件**：
- 修改 `backend/app/api/routes/files.py`：`_artifact_row()` 返回 `agent_id`；`list_artifacts()` 支持 `agent_id` 查询参数过滤。
- 修改 `backend/tests/test_phase17_artifact_meta.py`：断言产物 API 返回 `agent_id`，并覆盖命中/未命中 `agent_id` 过滤。
- 修改 `frontend/src/services/api.ts`：`ArtifactInfo` 增加 `agent_id`，`fetchArtifacts()` 增加 `agentId` 参数。
- 修改 `frontend/src/App.tsx`：`ArtifactsPage` 增加 Agent ID 过滤输入、筛选按钮，并在列表/详情展示 agent。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 30、M-U、G24 与本实现记录。

**核心代码变更**：
- 后端产物行新增 `agent_id: meta.get("agent_id", "")`，保持无侧车元数据时为空字符串兼容。
- `/api/v1/files/artifacts?agent_id=<id>` 会在已有 `kind`、`well_id` 过滤后继续按 `agent_id` 精确过滤。
- 前端调用 `fetchArtifacts(kind, '', agentId.trim())`，不改变原下载、预览和 Trace 跳转逻辑。

**遇到的问题与解决方案**：
- 问题：侧车元数据已有 `agent_id`，但 API 未透出，导致前端无法筛选。
  解决：最小扩展产物 row 字段和查询参数，不修改侧车文件格式。
- 问题：产物中心已有 kind 过滤，新增 Agent 过滤不能破坏原交互。
  解决：保留 kind select，新增 Agent 输入和筛选按钮；刷新仍使用当前状态加载。

**验证**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase16_artifacts.py backend/tests/test_phase17_artifact_meta.py` → 3 passed。
- `npm run build`（frontend）→ TypeScript 与 Vite 构建通过。
- `ReadLints` 检查 `files.py`、`test_phase17_artifact_meta.py`、`api.ts`、`App.tsx` → 无诊断。
- 仍观察到既有 OpenTelemetry `ValueError: I/O operation on closed file.` 非阻断警告，pytest 退出码为 0。

### [Phase 29.1] Prometheus Metrics 端点 — 已完成

**实现思路**：计划中 Metrics/Prometheus 仍属于可选增强，已有 `/monitor/stats` JSON 统计但不便于 Prometheus 抓取。本次不引入 `prometheus-client` 依赖，直接在监控路由中生成标准 text exposition：复用现有任务调度器、TraceStore、ApprovalService 与 ChannelManager 的运行期数据，输出任务状态、Trace 事件、审批待处理数和网关队列深度。这样保持实现轻量，同时不影响既有 JSON stats 和 timeline API。

**修改文件**：
- 修改 `backend/app/api/routes/monitor.py`：新增 `_escape_label()`、`_metric_line()` 与 `GET /monitor/metrics`。
- 修改 `backend/tests/test_phase12_observability.py`：新增 `test_monitor_metrics_prometheus_text`，覆盖内容类型和关键指标。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 29、M-T、G23 与本实现记录。

**核心代码变更**：
- `/monitor/metrics` 返回 `text/plain; version=0.0.4`，符合 Prometheus text exposition 基础格式。
- 指标包括 `boetclaw_tasks_total{status=...}`、`boetclaw_trace_events_total`、`boetclaw_trace_events_by_type{event_type=...}`、`boetclaw_approvals_pending`、`boetclaw_gateway_queue_depth{platform=...}`。
- `_escape_label()` 对反斜杠和双引号做转义，避免 label 值破坏 Prometheus 文本格式。

**遇到的问题与解决方案**：
- 问题：直接引入 Prometheus 客户端会增加新依赖和注册器生命周期管理成本。
  解决：先输出轻量文本指标，当前指标均是 gauge 类型，可由 Prometheus 直接抓取；后续如需 histogram/counter 再引入专用客户端。
- 问题：测试中创建任务会触发任务持久化，可能污染真实 workspace。
  解决：测试用 `monkeypatch` 将 `task_scheduler.store_path` 指向 `tmp_path`，并清空 `_tasks`。

**验证**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase12_observability.py` → 6 passed。
- `ReadLints` 检查 `backend/app/api/routes/monitor.py`、`backend/tests/test_phase12_observability.py` → 无诊断。
- 仍观察到既有 OpenTelemetry `ValueError: I/O operation on closed file.` 非阻断警告，pytest 退出码为 0。

### [Phase 28.1] LAS 文件上传导入闭环 — 已完成

**实现思路**：Phase 16.5 已完成 LAS 文本解析、路径导入、质量检查和曲线 JSON 沉淀，但前端只能填写服务器本地文件路径，普通用户无法从浏览器直接上传 LAS 文件。本次在不改变原路径导入接口和解析逻辑的前提下，新增 multipart 上传接口：后端接收文件后保存到 `workspace/domain/las_uploads/`，再复用 `import_las_file()` 完成解析、LasFile 记录创建、质量指标生成和 `las_curves/{las_id}.json` 曲线沉淀；前端 `/las/import` 同时提供“上传并质检”和“按路径导入”两种入口。

**修改文件**：
- 修改 `backend/app/api/routes/domain.py`：新增 `POST /domain/las/upload`，引入 `UploadFile`、`File`、`Form`，并增加 `_safe_upload_name()`。
- 修改 `backend/tests/test_phase16_las_import.py`：新增 multipart 上传导入测试，覆盖上传文件保存、LasFile 记录、质量指标和曲线 JSON。
- 修改 `frontend/src/services/api.ts`：新增 `uploadLasFile()`，使用 `FormData` 调用上传接口。
- 修改 `frontend/src/App.tsx`：`LasImportPage` 新增文件选择、上传处理和上传/路径两个按钮。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 28、M-S、G22 与本实现记录。

**核心代码变更**：
- `_safe_upload_name()` 使用 `Path(filename).name` 去掉目录，避免上传文件名包含路径片段。
- `upload_las()` 将文件写入 `settings.workspace_dir / "domain" / "las_uploads"`，再调用 `import_las_file(well_id, str(upload_path), safe_name)` 复用既有导入链路。
- `uploadLasFile()` 不手动设置 `Content-Type`，由浏览器为 `FormData` 生成 multipart boundary。
- `LasImportPage` 保留 `importLasFile()` 路径导入能力，新增 `selectedFile` 状态和 `uploadLasFile()` 上传导入能力。

**遇到的问题与解决方案**：
- 问题：原 LAS 导入接口只接收 JSON 路径，浏览器无法直接把本地文件路径交给后端读取。
  解决：新增 multipart 上传接口，先将文件写入 workspace，再进入原解析流程。
- 问题：上传文件名可能包含目录片段或为空。
  解决：通过 `_safe_upload_name()` 只保留 basename，空值回退到 `upload.las`。
- 问题：不希望维护两套解析和质量检查逻辑。
  解决：上传接口只负责保存文件，解析、状态、曲线数据和质量报告全部复用 `import_las_file()`。

**验证**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase16_las_import.py` → 3 passed。
- `npm run build`（frontend）→ TypeScript 与 Vite 构建通过。
- `ReadLints` 检查 `domain.py`、`test_phase16_las_import.py`、`api.ts`、`App.tsx` → 无诊断。
- 仍观察到既有 OpenTelemetry `ValueError: I/O operation on closed file.` 非阻断警告，pytest 退出码为 0。

### [Phase 27.1] 插件启停 `.env` 持久化 — 已完成

**实现思路**：Phase 15 已补齐插件安装、详情、启用/停用和错误隔离，但启停只修改进程内 `settings.enabled_plugins`；服务重启后仍按旧 `.env` 的 `ENABLED_PLUGINS` 加载，导致 UI 操作不具备重启恢复能力。本次复用 Provider 配置持久化阶段新增的 `update_env_file()`，在插件启停 API 更新运行期配置后同步写入 `backend/.env`，保持运行期和下次启动一致。

**修改文件**：
- 修改 `backend/app/api/routes/plugins.py`：新增 `PLUGIN_ENV_PATH`，在 `_set_enabled_plugin()` 中调用 `update_env_file({"ENABLED_PLUGINS": ...})`。
- 修改 `backend/tests/test_phase10_plugins.py`：插件治理测试注入临时 `.env`，断言启用写入、停用清空；错误隔离测试断言加载失败插件仍写入启用配置。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 27、M-R、G21 与本实现记录，并修正插件治理“持久化可后续增强”的旧表述。

**核心代码变更**：
- `_set_enabled_plugin(name, enabled)` 继续维护 `settings.enabled_plugins` 逗号列表，随后写入 `ENABLED_PLUGINS`，不改变 `reload_plugins()` 和前端接口响应结构。
- 测试通过 `monkeypatch.setattr(plugin_routes, "PLUGIN_ENV_PATH", tmp_path / ".env")` 隔离真实配置文件，避免测试污染开发环境。
- 停用最后一个插件时 `ENABLED_PLUGINS` 写为空字符串，`update_env_file()` 会格式化为 `ENABLED_PLUGINS=""`，下一次启动解析为空列表。

**遇到的问题与解决方案**：
- 问题：直接在测试里调用启停接口会写入真实 `backend/.env`。
  解决：在插件路由中引入可替换的 `PLUGIN_ENV_PATH` 常量，测试注入临时路径。
- 问题：启用失败插件时插件未 loaded，但用户明确开启的配置仍应保留，便于修复插件后重载。
  解决：持久化发生在更新启用列表后，`reload_plugins()` 即使捕获加载错误，也不会回滚 `ENABLED_PLUGINS`；测试覆盖该行为。

**验证**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase10_plugins.py` → 10 passed。
- `ReadLints` 检查 `backend/app/api/routes/plugins.py`、`backend/tests/test_phase10_plugins.py` → 无诊断。
- 仍观察到既有 OpenTelemetry `ValueError: I/O operation on closed file.` 非阻断警告，pytest 退出码为 0。

### [Phase 26.1] 渠道白名单控制台配置 — 已完成

**实现思路**：Phase 25 已完成渠道白名单后端 API，但运维人员仍需要通过接口手动修改配置，页面闭环不完整。本次沿用现有 `ChannelsManager` 页面，在“渠道配置状态与队列”和“消息历史”之间新增“渠道访问白名单”面板：加载渠道状态时同步读取 `GET /gateway/access-control`，按平台生成 textarea；用户可用换行或逗号填写 `user_id`，保存时调用 `PUT /gateway/access-control`。空输入保持开放策略，与后端兼容规则一致。

**修改文件**：
- 修改 `frontend/src/services/api.ts`：新增 `GatewayAccessPolicy`、`GatewayAccessControl` 类型，以及 `fetchGatewayAccessControl()`、`updateGatewayAccessControl()`。
- 修改 `frontend/src/components/ChannelsManager.tsx`：新增白名单草稿状态、解析/保存逻辑、白名单配置面板，并在消息历史筛选中加入 `denied`。
- 修改 `frontend/src/App.css`：新增 `.channel-access-card`、`.channel-access-grid`、`.channel-access-item` 样式。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 26、M-Q、G20 与本实现记录。

**核心代码变更**：
- `load()` 现在并行请求 `fetchGatewayStatus()`、`fetchGatewayMessages()`、`fetchGatewayAccessControl()`，并把后端 `allowed_users` 转成 textarea 的换行文本。
- `parseUsers()` 使用换行或逗号分隔，过滤空字符串；`buildAccessPayload()` 根据当前渠道列表构造 `{ channels: { [name]: { allowed_users } } }`。
- `handleSaveAccess()` 保存成功后用后端规范化结果回填草稿，并显示“渠道访问白名单已保存。”提示。

**遇到的问题与解决方案**：
- 问题：后端白名单是数组，页面输入更适合多行文本；需要避免用户输入空行导致无效 ID。
  解决：保存前统一按换行/逗号拆分并 trim，过滤空项，和后端规范化逻辑保持一致。
- 问题：消息历史原筛选项没有 `denied`，拒绝记录虽然已写入历史但页面不易定位。
  解决：在状态筛选下拉框中增加 `denied`，方便运营审计非白名单消息。

**验证**：
- `npm run build`（frontend）→ TypeScript 与 Vite 构建通过。
- `ReadLints` 检查 `ChannelsManager.tsx`、`api.ts`、`App.css` → 无诊断。

### [Phase 25.1] 渠道访问白名单与拒绝审计 — 已完成

**实现思路**：计划的访问控制章节明确要求“每渠道可配 `allowed_users`，非白名单消息拒绝并记录 `GATEWAY_MESSAGE{action:"denied"}`”。现有渠道网关已统一经过 `ChannelManager.enqueue()`，因此本次采用最小改动：新增 JSON-backed `AccessControlStore`，默认空白名单表示放行；在 webhook 入队前检查白名单，被拒绝时直接返回“Denied by access control”，不再触发原有 fallback 后台任务；同时在 `ChannelManager.enqueue()` 内也保留检查，覆盖 retry 或内部直接入队路径。

**修改文件**：
- 新增 `backend/app/services/gateway/access_control.py`：实现 `workspace/access_control.json` 的读取、更新、用户列表规范化和 `is_allowed()` 判断。
- 修改 `backend/app/services/gateway/manager.py`：新增 `is_allowed()`、`record_access_denied()`，并在 `enqueue()` 前执行白名单校验。
- 修改 `backend/app/api/routes/gateway.py`：webhook 入队前拦截拒绝用户；新增 `GET/PUT /gateway/access-control` 管理接口。
- 新增 `backend/tests/test_phase25_gateway_access_control.py`：覆盖配置持久化、非白名单拒绝、白名单用户正常入队。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 25、M-P、G19 与本实现记录。

**核心代码变更**：
- `AccessControlStore.list()` 每次从 JSON 读取并规范化为 `{ "channels": { platform: { "allowed_users": [...] } } }`，空列表表示该渠道开放。
- webhook 路由在 `enqueue()` 前调用 `channel_manager.is_allowed()`；拒绝时调用 `record_access_denied()`，返回成功响应但不创建任务、不进入队列、不走 fallback。
- `record_access_denied()` 会写入消息历史状态 `denied`，并发出 `EventType.GATEWAY_MESSAGE`，包含 `platform`、`action=denied`、`reason=user_not_allowed`、`user_id`。

**遇到的问题与解决方案**：
- 问题：原 webhook 逻辑在 `enqueue()` 返回 `False` 时会 fallback 到 `default_message_handler`，如果只在 `enqueue()` 内拒绝，非白名单消息仍可能被后台任务处理。
  解决：在 webhook 路由层先判断访问权限，拒绝后直接返回，不进入 `enqueue()` 和 fallback；同时保留 `enqueue()` 内校验保护 retry/内部入队路径。
- 问题：白名单功能不能破坏零配置渠道体验。
  解决：缺少配置文件、缺少平台策略或 `allowed_users=[]` 时均视为放行，只有显式配置非空白名单时才限制。

**验证**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase25_gateway_access_control.py backend/tests/test_phase15_gateway_ops.py backend/tests/test_phase8_channels.py` → 13 passed。
- `ReadLints` 检查 `access_control.py`、`manager.py`、`gateway.py`、`test_phase25_gateway_access_control.py` → 无诊断。
- 仍观察到既有 OpenTelemetry `ValueError: I/O operation on closed file.` 非阻断警告，pytest 退出码为 0。

### [Phase 24.1] 任务 JSON 持久化与重启恢复 — 已完成

**实现思路**：计划存储演进中仍将任务标记为 `TaskScheduler` 内存模型，导致服务重启后任务列表、执行结果、Trace/run 关联和 Agent 历史聚合都会丢失。本次沿用项目已有 JSON 持久化风格，在 `TaskScheduler` 内部直接接入 `workspace/tasks/task_history.json`：创建任务和状态更新后保存完整 `Task.to_dict()`；服务启动时加载历史任务。由于当前没有后台任务队列恢复机制，若加载到重启前处于 `running` 的任务，则将其标记为 `failed` 并记录“service restart interrupted”类错误，避免页面长期显示运行中。

**修改文件**：
- 修改 `backend/app/services/task_scheduler.py`：新增 `Task.from_dict()`、`store_path`、`_load()`、`_save()`，并在 `create()` 与 `update_status()` 后自动落盘。
- 新增 `backend/tests/test_phase24_task_persistence.py`：覆盖任务创建/更新落盘、重启加载、running 任务恢复为 failed。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 24、M-O、G18 与本实现记录。

**核心代码变更**：
- `TaskScheduler(store_path=...)` 默认写入 `settings.workspace_dir / "tasks" / "task_history.json"`，测试可注入临时路径，避免污染真实工作区。
- `_load()` 兼容文件不存在、JSON 解析失败、非列表结构和异常任务状态；正常任务恢复进 `_tasks` 后立即 `_save()`，以便把 `running -> failed` 的修正写回磁盘。
- `Task.from_dict()` 负责反序列化并做运行态修正，保留 `thread_id`、`trace_id`、`run_id`、`metadata` 等 Agent 历史与产物关联字段。

**遇到的问题与解决方案**：
- 问题：重启时无法继续执行已经处于 `running` 的后台任务，直接恢复为 running 会造成前端永远显示执行中。
  解决：恢复时将 `running` 标记为 `failed`，错误信息说明任务被服务重启中断，后续用户可通过现有“重跑”入口重新执行。
- 问题：新增持久化不应影响既有任务 API 和 Agent 历史聚合。
  解决：不改变 `TaskResponse` 和路由结构，只在调度器内部落盘；回归运行 Agent 历史测试确认 metadata 聚合仍可用。

**验证**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase24_task_persistence.py backend/tests/test_phase17_agent_index.py` → 3 passed。
- `ReadLints` 检查 `backend/app/services/task_scheduler.py`、`backend/tests/test_phase24_task_persistence.py` → 无诊断。
- 仍观察到既有 OpenTelemetry `ValueError: I/O operation on closed file.` 非阻断警告，pytest 退出码为 0。

### [Phase 23.1] API Token 鉴权与限流 — 已完成

**实现思路**：计划 G5 中仍保留“补 API 鉴权与限流落地”。本次采用最小可运行方案：新增统一 FastAPI 中间件保护 `/api/v1/*`，默认配置保持开放，只有 `API_TOKEN` 非空时才要求 `Authorization: Bearer <token>` 或 `X-API-Token`；新增 `API_RATE_LIMIT_PER_MINUTE`，默认 `0` 表示关闭，开启后按客户端 IP 做 60 秒滑动窗口计数。`/api/v1/monitor/health` 明确豁免，保证 Docker healthcheck 和外部探活不被 token 或限流阻断。

**修改文件**：
- 新增 `backend/app/middleware/api_security_mw.py`：实现 API Token 鉴权、内存限流和健康检查豁免。
- 修改 `backend/app/main.py`：注册 `ApiSecurityMiddleware`。
- 修改 `backend/app/core/config.py`：新增 `api_rate_limit_per_minute` 配置字段。
- 修改 `backend/.env.example`：新增 `API_RATE_LIMIT_PER_MINUTE=0` 示例。
- 新增 `backend/tests/test_phase23_api_security.py`：覆盖未授权 401、Bearer/X-API-Token 放行、健康检查豁免、超过限流返回 429。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 23/G17 与本实现记录。

**核心代码变更**：
```python
if not path.startswith(self.api_prefix) or self._is_health_path(path):
    return await call_next(request)
if not self._authorized(request):
    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
if self._rate_limited(request):
    return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
```

```python
if auth.lower().startswith("bearer ") and auth[7:] == expected:
    return True
return request.headers.get("x-api-token", "") == expected
```

**遇到的问题与解决方案**：
- 问题：默认本地开发和现有测试不能因为新增中间件被迫携带 token。
  解决：`API_TOKEN` 为空时鉴权完全关闭，沿用现有零配置体验。
- 问题：Docker healthcheck 调用 `/api/v1/monitor/health` 不携带鉴权头。
  解决：健康检查路径显式豁免鉴权与限流。
- 问题：全局 app 中间件状态可能影响测试隔离。
  解决：测试构造临时 FastAPI app 注册中间件，使用 monkeypatch 设置 `settings`，不依赖全局应用状态。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase23_api_security.py backend/tests/test_smoke.py`：`6 passed`。
- `ReadLints`：本次修改文件无诊断错误。

### [Phase 22.1] Trace 结构化时间线详情 — 已完成

**实现思路**：计划中可观测性已具备 trace、timeline、OTel 与 JSONL，但 `/trace/:traceId` 页面主要复用侧栏原始事件列表，缺少运行耗时、事件间隔和分类统计等细粒度信息。本次在不改变现有 raw trace API 的前提下增强 `build_timeline()` 输出：每个事件增加序号、相对起点偏移和与前一事件间隔，trace 级别增加起止时间与总耗时。前端 trace 页面接入 timeline API，以双栏方式展示结构化时间线和原始事件侧栏。

**修改文件**：
- 修改 `backend/app/core/timeline.py`：新增时间戳解析，补充 `sequence`、`offset_ms`、`delta_ms`、`started_at`、`ended_at`、`duration_ms`。
- 修改 `backend/tests/test_phase12_observability.py`：扩展 timeline 测试，覆盖总耗时和相邻事件间隔。
- 修改 `frontend/src/services/api.ts`：新增 `TraceTimeline`、`TimelineEvent` 类型和 `fetchTraceTimeline()`。
- 修改 `frontend/src/App.tsx`：`/trace/:traceId` 页面接入 `TraceTimelinePanel`，展示事件数、耗时、分类统计和事件详情。
- 修改 `frontend/src/App.css`：新增 trace 详情双栏、事件 marker、分类 pills 和移动端单栏样式。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 22/G16 与本实现记录。

**核心代码变更**：
```python
offset_ms = int((ts - start_ts).total_seconds() * 1000) if ts and start_ts else 0
delta_ms = int((ts - prev_ts).total_seconds() * 1000) if ts and prev_ts else 0
items.append({
    "sequence": idx + 1,
    "offset_ms": offset_ms,
    "delta_ms": delta_ms,
    "summary": _summarize(e),
    "data": e.data,
})
```

```tsx
<div className="trace-timeline-title">
  <strong>{event.summary}</strong>
  <span className="pill">{event.category}</span>
</div>
<p>{event.event_type} · +{event.offset_ms}ms · Δ {event.delta_ms}ms · run {event.run_id || '—'}</p>
```

**遇到的问题与解决方案**：
- 问题：现有 trace 页面已复用 `SidePanel`，直接替换会丢失原始事件 JSON。
  解决：采用双栏布局，左侧新增结构化 timeline，右侧保留原始事件侧栏。
- 问题：历史 trace 中 timestamp 可能格式异常。
  解决：新增 `_parse_ts()` 安全解析；解析失败时耗时字段退回 `0`，不影响 timeline 返回。
- 问题：后端 timeline API 已存在，不能破坏既有调用方。
  解决：只追加字段，保留原有 `trace_id`、`event_count`、`run_ids`、`categories`、`events[].data` 等字段。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase12_observability.py`：`5 passed`。
- `npm run build`：通过。
- `ReadLints`：本次修改文件无诊断错误。
- 注意：测试结束仍出现既有 OpenTelemetry `I/O operation on closed file` 警告，不影响测试退出码。

### [Phase 21.1] Plan 编辑确认与历史审计 — 已完成

**实现思路**：计划确认链路已有 `/plan`、interrupt 和 approve/reject，但 `PlanConfirmRequest.edited_todos` 只存在于 schema，前端未提供编辑 UI，后端也没有计划历史审计。此次补齐 edit 分支：前端确认卡支持将计划按行编辑后提交；后端在 `decision=edit` 时通过 `Command(resume={"decision":"edit","edited_todos":[...]})` 恢复图；同时新增轻量 JSON 审计仓库，记录计划创建、批准、拒绝、编辑动作和响应摘要，便于按 thread 追溯计划确认过程。

**修改文件**：
- 新增 `backend/app/memory/plan_history_store.py`：实现 `PlanHistoryStore`，读写 `workspace/plans/plan_history.json`。
- 修改 `backend/app/core/agent.py`：计划 interrupted 时记录 `created`；`confirm_plan()` 支持 `edited_todos`，记录 approve/reject/edit 历史。
- 修改 `backend/app/api/routes/agent.py`：`/agent/plan/confirm` 传递 `edited_todos`；新增 `GET /agent/plan/history`。
- 修改 `backend/tests/test_phase2_plan.py`：覆盖 approve 历史记录和 edit 恢复载荷。
- 修改 `frontend/src/services/api.ts`：`confirmPlan()` 支持 `editedTodos`。
- 修改 `frontend/src/components/PlanConfirm.tsx`：新增编辑模式、计划文本框和“提交编辑”动作。
- 修改 `frontend/src/components/Console.css`：新增计划编辑文本框样式。
- 修改 `docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`：新增 Phase 21/G15 与本实现记录。

**核心代码变更**：
```python
resume_value: Any = {"decision": decision, "edited_todos": edited_todos or []} if decision == "edit" else decision
result = await self.agent.ainvoke(Command(resume=resume_value), config=config)
plan_history_store.record(
    thread_id=thread_id,
    action=decision,
    edited_todos=edited_todos,
    response=str(content),
)
```

```tsx
const editedTodos = decision === 'edit'
  ? draft.split('\n').map(line => line.trim()).filter(Boolean)
  : undefined
const result = await confirmPlan(threadId, decision, editedTodos)
```

**遇到的问题与解决方案**：
- 问题：`edited_todos` 已存在于请求模型，但前端和后端确认逻辑没有使用。
  解决：保持原 approve/reject 行为不变，仅在 `decision === "edit"` 时传递结构化 resume payload。
- 问题：计划历史需要可追溯，但不宜引入数据库迁移。
  解决：沿用项目现有 JSON 持久化风格，落盘到 `workspace/plans/plan_history.json`。
- 问题：测试不能污染真实 workspace 历史。
  解决：测试通过 monkeypatch 将 `plan_history_store.path` 指向 `tmp_path`。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase2_plan.py`：`6 passed`。
- `npm run build`：通过。
- `ReadLints`：本次修改文件无诊断错误。

### [Phase 20.1] Provider 配置写入 `.env` — 已完成

**实现思路**：Provider 设置页此前已经可以通过 API 修改 API Key、base_url 和默认模型，但只更新运行期 `settings`，服务重启后会回到 `.env`/`.env.example` 中的旧值。本次沿用项目既有 `.env` 配置方式，不引入数据库：新增通用 `.env` 更新工具，保留文件中无关行与注释，只更新指定键；Provider 配置接口在运行期更新 settings 后，同步写入 `backend/.env`。这样 UI 写入立即生效，也能被后续启动加载。

**修改文件**：
- 新增 `backend/app/core/env_file.py`：实现 `update_env_file()`，支持保留原 `.env` 内容、更新已存在键、追加缺失键，并对空值/空白/注释字符做安全格式化。
- 修改 `backend/app/api/routes/providers.py`：`PUT /providers/{name}/config` 持久化 OpenAI/Anthropic API Key 与 base_url、Ollama base_url；`PUT /providers/default` 持久化 `LLM_PROVIDER` 与 `LLM_MODEL`。
- 修改 `backend/tests/test_phase6_providers.py`：新增临时 `.env` 持久化测试，避免污染真实配置。
- 修改 `docs/IMPLEMENTATION_PLAN.md`：新增 Phase 20、G14，并更新 Provider 基线状态。
- 修改 `docs/PROGRESS.md`：新增 Phase 20.1 清单项与本实现记录。

**核心代码变更**：
```python
def update_env_file(values: dict[str, str], path: Path | None = None) -> None:
    env_path = path or (BASE_DIR / ".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = {key.upper(): str(value) for key, value in values.items()}
    updated: list[str] = []
    # 遍历原文件，命中则原位更新，未命中则末尾追加
```

```python
settings.llm_provider = body.provider
settings.llm_model = body.model
update_env_file({"LLM_PROVIDER": body.provider, "LLM_MODEL": body.model}, PROVIDER_ENV_PATH)
```

**遇到的问题与解决方案**：
- 问题：Provider 写入需要持久化，但不能破坏 `.env` 中其他配置和注释。
  解决：`update_env_file()` 逐行解析，仅更新传入键；其他行原样保留，缺失键追加到末尾。
- 问题：真实 `backend/.env` 可能不存在。
  解决：工具函数在目标文件不存在时创建文件，并自动创建父目录。
- 问题：测试不能写真实 `.env` 或泄露 API Key。
  解决：测试通过 monkeypatch 将 `PROVIDER_ENV_PATH` 指向 `tmp_path/.env`，使用假 key 验证持久化结果。
- 问题：空值、包含空白或 `#` 的值直接写入可能被 dotenv 误读。
  解决：对这类值自动使用双引号并转义反斜杠和引号。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase6_providers.py`：`10 passed`。
- `ReadLints`：`backend/app/core/env_file.py`、`backend/app/api/routes/providers.py`、`backend/tests/test_phase6_providers.py` 无诊断错误。
- 注意：测试结束仍出现既有 OpenTelemetry `I/O operation on closed file` 警告，不影响测试退出码。

### [Phase 19.1] 审批历史 JSON 持久化与恢复 — 已完成

**实现思路**：安全设置页已经能查看待审批与审批历史，但历史数据只存放在 `ApprovalService._requests` 内存字典中，服务重启后会丢失。为保持现有 API 与前端不变，本次只在服务内部补持久化：`ApprovalService` 初始化时读取 `workspace/security/approval_history.json`，每次创建审批或裁决审批后将 `list_all()` 的结果写回 JSON。这样 `/security/approvals/history` 仍返回原结构，但数据具备跨重启恢复能力。

**修改文件**：
- 修改 `backend/app/security/approval.py`：新增 `ApprovalRequest.from_dict()`、`ApprovalService._load()`、`ApprovalService._save()`，并在 `create()`、`resolve()` 后自动保存。
- 修改 `backend/tests/test_phase3_security.py`：新增审批历史持久化测试，覆盖创建、裁决、落盘和新服务实例恢复。
- 修改 `docs/IMPLEMENTATION_PLAN.md`：新增 Phase 19、G13，并更新 ToolGuard 基线状态。
- 修改 `docs/PROGRESS.md`：新增 Phase 19.1 清单项与本实现记录。

**核心代码变更**：
```python
class ApprovalService:
    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path or (settings.workspace_dir / "security" / "approval_history.json")
        self._requests: dict[str, ApprovalRequest] = {}
        self._load()

    def _save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [r.to_dict() for r in self.list_all()]
        self.persist_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
```

```python
def create(self, tool: str, args: dict, findings: list[dict], thread_id: str = "") -> ApprovalRequest:
    req = ApprovalRequest(id=uuid.uuid4().hex[:12], tool=tool, args=args, findings=findings, thread_id=thread_id)
    self._requests[req.id] = req
    self._save()
    return req
```

**遇到的问题与解决方案**：
- 问题：需要持久化历史，但不能改变 `/security/approvals` 与 `/security/approvals/history` 的响应结构，避免影响前端安全页。
  解决：持久化逻辑封装在 `ApprovalService` 内部，`ApprovalRequest.to_dict()` 输出保持不变。
- 问题：历史文件可能不存在、为空或 JSON 损坏。
  解决：`_load()` 对文件不存在、IO 错误和 JSON 解析错误采用安全返回，不阻断服务启动。
- 问题：测试不能污染真实工作区历史。
  解决：测试通过 `ApprovalService(persist_path=tmp_path / ...)` 注入临时路径，隔离真实数据。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase3_security.py`：`11 passed`。
- `ReadLints`：`backend/app/security/approval.py`、`backend/tests/test_phase3_security.py` 无诊断错误。

### [Phase 18.1] Docker Compose 端到端冒烟与前端浏览器回归 — 已完成

**实现思路**：总验收清单中最后剩余项是 `docker compose up` 端到端冒烟与前端浏览器回归。本次按部署路径进行真实验证：先启动 Docker Desktop Engine，再执行 `docker compose up --build -d`，确认 backend/frontend 容器运行状态；随后通过 HTTP 检查后端健康接口、OpenAPI 文档和前端静态入口；最后使用浏览器打开 Docker 前端地址，逐个验证核心页面路由可访问并出现关键控件。

**修改文件**：
- 修改 `docs/IMPLEMENTATION_PLAN.md`：将总验收清单中的 `docker compose up` 端到端冒烟与前端浏览器回归勾选为完成。
- 修改 `docs/PROGRESS.md`：新增 Phase 18.1 清单项，并追加本实现记录。

**核心执行与验证**：
```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/monitor/health"
Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing
```

**浏览器回归覆盖页面**：
- `/chat`：聊天页正常渲染，导航、快捷任务、输入框和任务侧栏可见。
- `/tasks`：任务页正常渲染，状态筛选、刷新、新建入口可见。
- `/agents`：Agent 工作区页正常渲染，default 工作区和删除保护可见。
- `/wells`：井数据页正常渲染，新建井表单和刷新入口可见。
- `/artifacts`：产物中心正常渲染，类型筛选和刷新入口可见。
- `/settings/security`：安全设置页正常渲染，Guard level 下拉和安全设置区可见。

**遇到的问题与解决方案**：
- 问题：首次执行 `docker compose up --build -d` 失败，提示 `dockerDesktopLinuxEngine` 管道不存在。
  解决：确认 Docker 客户端已安装但 Docker Desktop Engine 未启动；启动 Docker Desktop 后轮询 `docker info`，待返回 `docker-ready` 后重试 Compose。
- 问题：首次完整构建耗时较长，后端镜像需要下载 Debian 包和 Python 依赖。
  解决：将 Compose 构建放入后台并持续等待完成；最终构建启动成功，backend 容器状态为 `healthy`，frontend 容器正常运行。

**验证结果**：
- `docker compose up --build -d`：通过。
- `docker compose ps`：backend `healthy`，frontend `Up`。
- `GET /api/v1/monitor/health`：`status=healthy`、`ready=true`、`agent_ready=true`。
- `GET /docs`：HTTP 200。
- `GET http://127.0.0.1:5173`：HTTP 200。
- 浏览器回归：核心路由均正常渲染。

### [Phase 17.2] 产物侧车元数据自动写入 — 已完成

**实现思路**：Phase 16.4 的产物中心已经会读取 `workspace/artifacts/{kind}_{filename}.json`，但图表/代码生成工具不会自动写入侧车文件，导致 task、Trace、井号关联依赖人工预置。本次新增运行上下文 `ContextVar`，在 Agent 运行入口设置当前 `task_id`、`agent_id`、`well_id`，复用既有 `trace_id_var`、`run_id_var`；`generate_chart` 和 `generate_code` 保存产物后统一写 sidecar JSON。任务执行会从 `Task.metadata` 传入 `agent_id` 与 `well_id`，图表工具还会从输入数据行中推断 `well_id/well_ref/well`，让产物中心自动读出关联字段。

**修改文件**：
- 新增 `backend/app/core/run_context.py`：定义 task/agent/well 运行上下文，并提供 `write_artifact_meta()`。
- 修改 `backend/app/core/agent.py`：单 Agent `invoke()` 与 `stream()` 设置并重置产物上下文。
- 修改 `backend/app/agents/runtime.py`：多 Agent `invoke_agent()` 设置并重置产物上下文。
- 修改 `backend/app/api/routes/tasks.py`：任务后台执行时传入 `task_id`、`metadata.agent_id`、`metadata.well_id`。
- 修改 `backend/app/api/routes/agent.py`：聊天接口向运行入口传递当前 Agent ID。
- 修改 `backend/app/tools/builtin.py`：`generate_chart()`、`generate_code()` 生成文件后自动写 `.meta.json`。
- 新增 `backend/tests/test_phase17_artifact_meta.py`：覆盖代码产物侧车写入与产物中心读取 task/trace/run/agent/well。
- 修改 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`：勾选 17.2 并补充本实现记录。

**核心代码变更**：
```python
def write_artifact_meta(kind: str, filename: str, *, well_id: str = "", extra: dict[str, Any] | None = None) -> Path:
    artifacts_dir = settings.workspace_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id_var.get(),
        "trace_id": trace_id_var.get(),
        "run_id": run_id_var.get(),
        "agent_id": agent_id_var.get(),
        "well_id": well_id or well_id_var.get(),
    }
    if extra:
        meta.update({k: v for k, v in extra.items() if v not in (None, "")})
    meta_path = artifacts_dir / f"{kind}_{filename}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path
```

```python
write_artifact_meta(
    "chart",
    filename,
    well_id=_infer_well_id(data if isinstance(data, list) else []),
    extra={"title": title, "chart_type": chart_type},
)
```

**遇到的问题与解决方案**：
- 问题：工具函数无法直接知道当前任务、Trace、Agent 或井号。
  解决：新增 `run_context.py`，用 `ContextVar` 在 Agent 调用链内传递上下文，并在 `finally` 中 reset，避免跨请求串值。
- 问题：井号可能不来自任务 metadata，而是来自 `query_drilling_params` 返回的数据。
  解决：`generate_chart()` 在输入数据行中推断 `well_id`、`well_ref` 或 `well`，优先写入 sidecar。
- 问题：非任务聊天没有 `task_id/well_id`。
  解决：仍写入 `trace_id`、`run_id`、`agent_id` 和创建时间；任务触发场景则补齐 task/well。
- 问题：后端测试结束仍出现既有 OpenTelemetry 关闭流警告。
  解决：该警告不影响测试退出码，延续记录为既有非阻塞问题。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase17_agent_index.py backend/tests/test_phase17_artifact_meta.py`：通过。
- `npm run build`：通过。
- `ReadLints`：本次修改文件无 IDE 诊断错误。

### [Phase 17.1] Agent 工作区运行历史与文件索引 — 已完成

**实现思路**：此前 `/agents/:agentId` 已能展示工作区详情、删除非 default Agent 与技能聚合，但“最近运行”和“files 目录索引”仍是占位说明。本次按现有数据边界做最小闭环：后端新增 Agent 专用文件索引接口，递归读取当前工作区 `files` 目录并返回相对路径、大小和修改时间；运行历史接口从现有内存任务调度器与 JSON 会话历史中汇总与 Agent 相关的记录，并通过 `match_source` 标明关联依据，避免把弱关联误当成强绑定。前端 Agent 详情页选中工作区后并行加载详情、文件索引和运行历史，替换原占位提示。

**修改文件**：
- 修改 `backend/app/api/routes/agents.py`：新增 `GET /agents/{agent_id}/files` 和 `GET /agents/{agent_id}/history`。
- 新增 `backend/tests/test_phase17_agent_index.py`：覆盖工作区文件索引、任务历史与会话历史聚合。
- 修改 `frontend/src/services/api.ts`：新增 `AgentFileInfo`、`AgentHistoryItem` 类型与 `fetchAgentFiles()`、`fetchAgentHistory()`。
- 修改 `frontend/src/App.tsx`：`AgentsPage` 选中 Agent 时并行加载详情、files、history，并展示运行历史与文件列表。
- 修改 `frontend/src/App.css`：新增 Agent 历史/文件双栏布局与移动端降级样式。
- 修改 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`：勾选 17.1 并同步基线、验收清单和实现记录。

**核心代码变更**：
```python
@router.get("/{agent_id}/files")
async def list_agent_files(agent_id: str):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    files_dir = ws.files_dir()
    rows = []
    if files_dir.exists():
        for path in files_dir.rglob("*"):
            if path.is_file():
                stat = path.stat()
                rows.append({
                    "path": str(path.relative_to(files_dir)).replace("\\", "/"),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                })
    return {"agent_id": agent_id, "root": str(files_dir), "files": rows}
```

```tsx
const [detail, files, history] = await Promise.all([
  fetchAgent(selectedAgentId),
  fetchAgentFiles(selectedAgentId),
  fetchAgentHistory(selectedAgentId),
])
setSelected(detail)
setAgentFiles(files.files)
setAgentHistory(history.history)
```

**遇到的问题与解决方案**：
- 问题：现有 `Task` 数据模型没有强制 `agent_id` 一等字段，不能无条件把所有任务归属到某个 Agent。
  解决：历史接口只采信 `task.metadata.agent_id` 的强关联；仅对非 default Agent 保留标题包含 Agent ID 的弱关联，并在返回值中用 `match_source` 明确来源。
- 问题：首次在根环境运行 `pytest` 时缺少 `structlog`，导致导入失败。
  解决：确认项目已有 `backend/.venv`，改用 `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase17_agent_index.py` 运行并通过。
- 问题：测试结束仍出现既有 OpenTelemetry `ValueError: I/O operation on closed file.` 警告。
  解决：该警告与此前阶段一致，不影响 pytest 退出码和本次断言结果，记录为既有非阻塞问题。

**验证结果**：
- `.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase17_agent_index.py`：通过。
- `npm run build`：通过。
- `ReadLints`：本次修改文件无 IDE 诊断错误。

### [Phase 16.5] LAS 导入、质量检查与曲线沉淀 — 已完成

**实现思路**：16.2 已有 LAS 登记页，但未解析文件内容。本次新增轻量 LAS 文本解析器，支持常见 `~Curve` 与 `~A` 段：提取曲线名、数据行、深度范围、空值数量和警告信息。导入 API 校验井存在，读取 LAS 文件，生成 `LasFile` 记录并把曲线数据沉淀到 `workspace/domain/las_curves/{las_id}.json`；前端 `/las/import` 页面改为“导入并质检”，列表展示状态、曲线、深度范围、点数和空值数。

**修改文件**：
- 修改 `backend/app/domain/models.py`：`LasFile` 新增 `curve_data_path`、`quality` 字段。
- 新增 `backend/app/domain/las_importer.py`：实现 `parse_las_text()` 与 `import_las_file()`。
- 修改 `backend/app/api/routes/domain.py`：新增 `POST /domain/las/import`。
- 新增 `backend/tests/test_phase16_las_import.py`：覆盖 LAS 文本解析质量指标和导入后曲线 JSON 沉淀。
- 修改 `frontend/src/services/api.ts`：扩展 `LasFile` 类型并新增 `importLasFile()`。
- 修改 `frontend/src/App.tsx`：增强 `/las/import` 页面，支持文件路径导入、错误展示和质量结果列表。
- 修改 `docs/PROGRESS.md`：勾选 16.5 并追加本实现记录。

**核心代码变更**：
```python
def parse_las_text(text: str) -> dict[str, Any]:
    ...
    if section == "~C":
        name = line.split(".", 1)[0].strip()
        curves.append(name)
    elif section == "~A":
        row[name] = None if parsed == NULL_VALUE else parsed
```

```python
curve_path = curve_dir / f"{las['id']}.json"
curve_path.write_text(json.dumps(parsed["rows"], ensure_ascii=False, indent=2), encoding="utf-8")
updated = domain_store.update("las_files", las["id"], {"curve_data_path": str(curve_path), "quality": parsed["quality"]})
```

**问题与解决**：
- 问题：项目没有 LAS 专用解析依赖，也没有文件上传链路。
- 解决：先实现无依赖文本解析器和“路径导入”接口，覆盖常见 LAS `~Curve`/`~A` 数据段；上传能力可后续补充。
- 问题：LAS 空值需要计入质量报告。
- 解决：将 `-999.25` 识别为 `None`，统计 `null_count`，并记录点数、曲线数、深度范围。
- 问题：曲线数据可能较大，不宜直接塞进 LasFile 记录。
- 解决：曲线行数据单独写入 `domain/las_curves/{las_id}.json`，LasFile 只保存 `curve_data_path` 和质量摘要。

**验证**：
- `ReadLints` 检查 LAS 导入后端、测试、前端页面与 API → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase16_las_import.py -q` → 2 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-C6L8ht2B.js 410.57KB`、`index-D8bG48L3.css 23.68KB`。

### [Phase 16.4] 产物中心与预览下载 — 已完成

**实现思路**：已有 `generate_chart` 和 `generate_code` 会分别写入 `workspace/charts`、`workspace/code`，但没有统一产物中心。本次不改变工具输出路径，在文件服务中新增产物索引 API：扫描图表和代码目录，返回类型、文件名、大小、预览 URL、下载 URL，以及预留的 `task_id`、`trace_id`、`well_id` 关联元数据。前端新增 `/artifacts` 页面，支持类型筛选、图表预览、代码预览和下载。

**修改文件**：
- 修改 `backend/app/api/routes/files.py`：新增 `GET /files/artifacts`、`GET /files/artifacts/{kind}/{filename}/download`；补安全路径校验和代码 preview。
- 新增 `backend/tests/test_phase16_artifacts.py`：覆盖产物列表、代码预览、下载和不安全路径拒绝。
- 修改 `frontend/src/services/api.ts`：新增 `ArtifactInfo` 类型和 `fetchArtifacts()`。
- 修改 `frontend/src/App.tsx`：新增 `/artifacts` 路由、顶部导航和 `ArtifactsPage`。
- 修改 `frontend/src/App.css`：新增产物中心布局和图表预览样式。
- 修改 `docs/PROGRESS.md`：勾选 16.4 并追加本实现记录。

**核心代码变更**：
```python
@router.get("/artifacts")
async def list_artifacts(kind: str = "", well_id: str = ""):
    rows = []
    if kind in ("", "chart") and charts_dir.exists():
        rows.extend(_artifact_row("chart", path) for path in charts_dir.glob("*.png") if path.is_file())
    if kind in ("", "code") and code_dir.exists():
        rows.extend(_artifact_row("code", path) for path in code_dir.iterdir() if path.is_file())
    return {"artifacts": rows}
```

```tsx
{selected.kind === 'chart' ? (
  <div className="artifact-preview">
    <img src={selected.url} alt={selected.filename} />
  </div>
) : (
  <pre>{selected.preview || '—'}</pre>
)}
```

**问题与解决**：
- 问题：现有工具没有写任务/Trace/井号元数据。
- 解决：产物 API 预留 `task_id`、`trace_id`、`well_id` 字段，并支持读取 `workspace/artifacts/{kind}_{filename}.json` 侧车元数据；没有元数据时字段为空，不影响预览下载。
- 问题：下载接口不能允许路径穿越。
- 解决：新增 `_safe_file()`，目标路径必须解析在 charts/code 目录内。
- 问题：图表和代码预览方式不同。
- 解决：图表返回 image URL，代码读取前 2000 字符作为 preview。

**验证**：
- `ReadLints` 检查文件服务、产物测试、前端产物页面与 API → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase16_artifacts.py -q` → 2 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-DkenEd0Y.js 410.80KB`、`index-D8bG48L3.css 23.68KB`。

### [Phase 16.3] `query_drilling_params` 接入领域参数库 — 已完成

**实现思路**：原 `query_drilling_params` 完全生成模拟数据，无法使用 16.1/16.2 沉淀的真实参数。本次只改该工具：先从 `domain_store` 查询 Well 与 DrillingParam，支持按井 `id` 或井名匹配；若指定深度范围内存在真实参数，则返回 `source=domain` 和按井深排序的真实记录；如果没有领域数据、井不存在或读取异常，则保留原模拟数据 fallback，返回 `source=mock`，确保现有 Agent 调用不被破坏。

**修改文件**：
- 修改 `backend/app/tools/builtin.py`：`query_drilling_params` 优先读取 `domain_store` 的 `params` 集合；新增 `_mock_drilling_params()` 保留原模拟逻辑。
- 新增 `backend/tests/test_phase16_domain_tools.py`：覆盖领域数据命中与 mock fallback。
- 修改 `docs/PROGRESS.md`：勾选 16.3 并追加本实现记录。

**核心代码变更**：
```python
matched_well = next((w for w in wells if w.get("id") == well_id or w.get("name") == well_id), None)
lookup_id = matched_well["id"] if matched_well else well_id
for row in domain_store.list("params", lookup_id):
    depth = float(row.get("measured_depth", 0))
    if start <= depth <= end:
        domain_records.append({...})
```

```python
if domain_records:
    result = {
        "well_id": well_id,
        "depth_range": depth_range,
        "source": "domain",
        "records": domain_records,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
```

**问题与解决**：
- 问题：用户可能传井名 `XX-1`，而参数记录按内部 `well_id` 存储。
- 解决：工具先在 wells 中用 `id` 或 `name` 匹配，匹配后用内部 id 查询参数，并在返回中保留井名和 `well_ref`。
- 问题：历史调用依赖 mock 数据，不能因没有真实数据而失败。
- 解决：领域数据不存在、为空或读取异常时统一回退 `_mock_drilling_params()`。
- 问题：深度范围可能传入异常字符串。
- 解决：解析失败时使用默认 `0-3000` 范围，并继续 fallback 语义。

**验证**：
- `ReadLints` 检查 `builtin.py` 与工具测试 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase16_domain_tools.py -q` → 2 passed。

### [Phase 16.2] 领域页面与前端路由 — 已完成

**实现思路**：在 16.1 领域 API 基础上，复用 Phase 14 的轻量 History API 路由层，新增井数据与领域记录页面。页面先覆盖核心数据维护闭环：`/wells` 创建和查看井列表，`/wells/:wellId` 聚合展示井段、日报、参数、LAS 文件，并支持新增井段；`/reports`、`/params`、`/las/import` 分别提供日报、钻井参数、LAS 文件登记表单和记录列表。实际 LAS 解析、质量检查和工具真实数据源在后续 16.3/16.5 接入。

**修改文件**：
- 修改 `frontend/src/services/api.ts`：新增 `Well`、`WellboreSection`、`DailyReport`、`DrillingParam`、`LasFile` 类型，以及领域 API 调用函数。
- 修改 `frontend/src/App.tsx`：新增 `/wells`、`/wells/:wellId`、`/reports`、`/params`、`/las/import` 路由解析、顶部导航和页面组件。
- 修改 `frontend/src/App.css`：新增领域页面双栏布局、统计卡片和表单样式。
- 修改 `docs/PROGRESS.md`：勾选 16.2 并追加本实现记录。

**核心代码变更**：
```tsx
if (path === '/wells') return { page: 'wells' }
if (path.startsWith('/wells/')) {
  return { page: 'wells', wellId: decodeURIComponent(path.slice('/wells/'.length)) }
}
if (path === '/reports') return { page: 'reports' }
if (path === '/params') return { page: 'params' }
if (path === '/las/import') return { page: 'las-import' }
```

```tsx
const [w, s, r, p, l] = await Promise.all([
  fetchWell(wellId),
  fetchWellSections(wellId),
  fetchDailyReports(wellId),
  fetchDrillingParams(wellId),
  fetchLasFiles(wellId),
])
```

**问题与解决**：
- 问题：领域页面需要多个对象联动，但还没有全局状态管理。
- 解决：每个页面用局部 `load()` 聚合 API 数据，创建记录后重新加载，避免引入额外状态库。
- 问题：LAS 导入在 16.2 只要求页面路由，真实解析属于 16.5。
- 解决：当前页面做“登记”闭环，记录文件名、路径、曲线和深度范围；后续解析服务可复用这些记录。
- 问题：没有井时日报/参数/LAS 表单无法关联。
- 解决：页面显示“请先创建井”的空状态，并在有井时默认选中第一口井。

**验证**：
- `ReadLints` 检查 `App.tsx`、`App.css`、`api.ts` → 无诊断。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-DMpE__1X.js 407.72KB`、`index-C0-Epx8M.css 23.41KB`。

### [Phase 16.1] 钻井领域模型与 JSON 仓库 — 已完成

**实现思路**：Phase 16 需要从“智能体外壳 + 模拟工具”进入真实业务对象沉淀。本次先落地后端领域数据基座，不引入数据库迁移，沿用项目已有 JSON 持久化风格，在 `workspace/domain/domain_data.json` 中管理井、井段、日报、钻井参数和 LAS 文件注册记录。API 先提供稳定 CRUD/列表能力，后续 16.2 页面、16.3 工具真实数据源、16.5 LAS 导入都基于这些对象扩展。

**修改文件**：
- 新增 `backend/app/domain/__init__.py`：领域包入口。
- 新增 `backend/app/domain/models.py`：定义 `Well`、`WellboreSection`、`DailyReport`、`DrillingParam`、`LasFile`。
- 新增 `backend/app/domain/store.py`：实现 `DomainStore`，支持 JSON 加载、保存、列表、详情、创建、更新、删除。
- 新增 `backend/app/api/routes/domain.py`：新增 `/api/v1/domain/wells`、`/sections`、`/reports`、`/params`、`/las-files` API。
- 修改 `backend/app/main.py`：注册领域路由。
- 新增 `backend/tests/test_phase16_domain.py`：覆盖 JSON 仓库 CRUD、领域 API 创建关联对象、缺失井关联校验。
- 修改 `docs/PROGRESS.md`：勾选 16.1 并追加本实现记录。

**核心代码变更**：
```python
class Well(DomainBase):
    name: str
    field: str = ""
    operator: str = ""
    location: str = ""
    status: str = "planned"
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
def create(self, collection: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = self.load()
    now = datetime.now(timezone.utc).isoformat()
    item = {**payload, "id": payload.get("id") or uuid.uuid4().hex[:12], "created_at": now, "updated_at": now}
    data[collection].append(item)
    self.save(data)
    return item
```

```python
@router.post("/params", response_model=DrillingParam)
async def create_param(body: DrillingParamIn):
    _require_well(body.well_id)
    return domain_store.create("params", body.model_dump())
```

**问题与解决**：
- 问题：计划中允许 SQLite/Postgres 或文件索引，当前项目尚无数据库迁移体系。
- 解决：采用 JSON 仓库作为最小可验证持久化实现，保持与 Cron、会话等现有持久化风格一致；后续可平滑迁移到 SQLite/Postgres。
- 问题：井段、日报、参数、LAS 文件必须关联真实井，不能产生孤儿数据。
- 解决：领域路由在创建关联对象前调用 `_require_well(well_id)`，缺失井时返回 404。
- 问题：后续页面和工具需要按井过滤子对象。
- 解决：列表接口统一支持 `well_id` 查询参数，如 `/domain/params?well_id=...`。

**验证**：
- `ReadLints` 检查领域模型、仓库、路由、主应用和测试文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase16_domain.py -q` → 3 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。

### [Phase 15.5] 调度增强与运行历史 — 已完成

**实现思路**：原 Cron 支持创建、删除、持久化和 APScheduler 触发，但缺少编辑、启停、手动触发和运行历史。本次在 `CronService` 中扩展 job 状态字段与运行记录，新增更新/启停/手动触发/历史查询方法；后端接入对应 REST API；前端调度页支持行内编辑、启停、立即触发，并展示最近运行历史、失败原因、trace/run 信息。

**修改文件**：
- 修改 `backend/app/services/cron_service.py`：`CronJob` 新增 `last_status`、`last_error`、`run_count`；新增 `CronRunRecord`；新增 `update_job()`、`set_enabled()`、`trigger()`、`history()`；执行时记录成功/失败历史。
- 修改 `backend/app/api/routes/cron.py`：新增 `PUT /tasks/cron/{job_id}`、`POST /tasks/cron/{job_id}/enable`、`POST /tasks/cron/{job_id}/trigger`、`GET /tasks/cron/history`。
- 修改 `backend/tests/test_phase9_scheduler.py`：覆盖编辑、启停、手动触发、失败历史与禁用后不可触发。
- 修改 `frontend/src/services/api.ts`：新增 Cron 状态字段、`CronRunRecord` 类型及 `updateCronJob()`、`setCronEnabled()`、`triggerCronJob()`、`fetchCronHistory()`。
- 修改 `frontend/src/components/CronManager.tsx`：新增行内编辑、保存、启停、触发、运行历史展示。
- 修改 `frontend/src/App.css`：新增 Cron 编辑网格样式。
- 修改 `docs/PROGRESS.md`：勾选 15.5 并追加本实现记录。

**核心代码变更**：
```python
async def trigger(self, job_id: str) -> CronRunRecord | None:
    job = self._jobs.get(job_id)
    if job is None:
        return None
    return await self._run_job(job_id, manual=True)
```

```python
record.status = "failed"
record.error = str(exc)
job.last_status = "failed"
job.last_error = str(exc)
record.finished_at = datetime.now(timezone.utc).isoformat()
```

```tsx
<button className="mgr-btn secondary" disabled={!j.enabled} onClick={() => void handleTrigger(j)}>
  <Play size={12} /> 触发
</button>
```

**问题与解决**：
- 问题：编辑 Cron 表达式时需要同步 APScheduler 中已有 job。
- 解决：`update_job()` 持久化后移除旧调度项，若 job 仍启用则重新 `_schedule(job)`。
- 问题：手动触发禁用任务会造成语义不清。
- 解决：`trigger()` 复用 `_run_job()` 的 enabled 检查，禁用或不存在返回 `None`，API 转为 404。
- 问题：失败原因此前只写日志，UI 不可见。
- 解决：`CronRunRecord.error` 和 `CronJob.last_error` 同步记录，前端历史和任务列表都展示。

**验证**：
- `ReadLints` 检查调度后端、测试、前端调度组件与样式文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase9_scheduler.py -q` → 7 passed。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-CNmlhZub.js 392.60KB`、`index-BA8cPJ6o.css 23.15KB`。

### [Phase 15.4] 渠道运维与消息审计 — 已完成

**实现思路**：渠道网关已有钉钉/飞书/QQ/Telegram webhook 与异步队列，但缺少运维视图和消息审计。本次不改变 webhook 主路径，只在 `ChannelManager` 中加入运行期消息历史，记录入队、失败、回发等状态；后端新增渠道状态、消息历史、失败重试接口；前端新增 `/settings/channels` Tab 展示配置状态、队列深度、消费者状态、消息历史、失败重试、任务/Trace/回发记录字段。

**修改文件**：
- 修改 `backend/app/services/gateway/manager.py`：新增 `status()`、`record_message()`、`message_history()`、`retry_message()`；`enqueue()` 记录 queued/failed。
- 修改 `backend/app/api/routes/gateway.py`：默认消息处理记录回发成功/失败；新增 `GET /gateway/status`、`GET /gateway/messages`、`POST /gateway/messages/{record_id}/retry`。
- 新增 `backend/tests/test_phase15_gateway_ops.py`：覆盖渠道状态、历史查询、失败消息重试。
- 修改 `frontend/src/services/api.ts`：新增渠道状态、消息记录、重试 API 类型和封装。
- 新增 `frontend/src/components/ChannelsManager.tsx`：实现渠道状态卡片、队列深度、消息过滤、失败重试和回发字段展示。
- 修改 `frontend/src/App.tsx`：新增 `/settings/channels` 设置 Tab。
- 修改 `frontend/src/App.css`：新增渠道统计和过滤表单样式。
- 修改 `docs/PROGRESS.md`：勾选 15.4 并追加本实现记录。

**核心代码变更**：
```python
def record_message(self, platform: str, message: GatewayMessage, status: str, detail: str = "", *, task_id: str = "", trace_id: str = "") -> dict[str, Any]:
    record = {
        "id": uuid.uuid4().hex[:12],
        "platform": platform,
        "status": status,
        "detail": detail,
        "message_id": message.message_id,
        "chat_id": message.chat_id,
        "task_id": task_id,
        "trace_id": trace_id,
        "_message": message,
    }
    self._history.insert(0, record)
    return record
```

```tsx
{msg.status === 'failed' && (
  <button className="mgr-btn secondary" onClick={() => void handleRetry(msg.id)}>重试</button>
)}
```

**问题与解决**：
- 问题：渠道消息来自外部平台，不能为了运维视图改变 webhook 响应语义。
- 解决：只在管理器层增加运行期审计记录，原 webhook 入队和 fallback 行为保持不变。
- 问题：失败重试需要原始消息对象，但 API 响应不能暴露 Python 对象。
- 解决：历史记录内部保留 `_message`，对外返回时剔除；重试接口根据 record id 重新 enqueue 原始消息。
- 问题：Phase 15.4 初始实现时消息历史尚未落盘。
- 解决：先提供运行期运维闭环；已在 Phase 34 补齐 JSON 持久化，服务重启后可恢复查询。

**验证**：
- `ReadLints` 检查渠道后端、测试、前端渠道管理与样式文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase15_gateway_ops.py -q` → 1 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-DdQqJ5Nn.js 389.13KB`、`index-CTuWo3dL.css 22.81KB`。

### [Phase 15.3] MCP 管理页与工具详情 — 已完成

**实现思路**：原 MCP 能力已由 `mcp_manager` 在启动/重载时连接，并在工具侧栏中混合展示 MCP 工具，但缺少独立管理入口。本次在现有 `/tools/mcp/servers`、`/tools/mcp/reload` 基础上增强返回结构，并新增 MCP 工具详情 API；前端新增 `/settings/mcp` Tab，展示 server 配置/连接状态、MCP 工具列表、单工具参数 schema、reload 返回结果。

**修改文件**：
- 修改 `backend/app/tools/mcp_manager.py`：新增 `list_tool_details()`、`get_tool_detail()`、`list_server_statuses()`。
- 修改 `backend/app/api/routes/tools.py`：增强 `GET /tools/mcp/servers` 和 `POST /tools/mcp/reload`；新增 `GET /tools/mcp/tools`、`GET /tools/mcp/tools/{name}`。
- 新增 `backend/tests/test_phase15_mcp.py`：覆盖 server 状态、工具列表和单工具详情。
- 修改 `frontend/src/services/api.ts`：新增 MCP server/tool/reload 类型和 API 封装。
- 新增 `frontend/src/components/McpManager.tsx`：实现 server 状态、reload、工具列表和参数 schema 详情。
- 修改 `frontend/src/App.tsx`：新增 `/settings/mcp` 设置 Tab。
- 修改 `frontend/src/App.css`：新增 MCP 工具双栏布局样式。
- 修改 `docs/PROGRESS.md`：勾选 15.3 并追加本实现记录。

**核心代码变更**：
```python
def list_server_statuses(self) -> list[dict[str, Any]]:
    configured = settings.get_mcp_servers_config()
    names = set(configured) | set(self._servers)
    return [
        {
            "name": name,
            "configured": name in configured,
            "connected": name in self._servers,
            "config": configured.get(name, self._servers.get(name, {})),
        }
        for name in sorted(names)
    ]
```

```tsx
const result = await reloadMcp()
setLastReload(result)
setServers(result.servers)
setTools(result.mcp_tool_details)
```

**问题与解决**：
- 问题：原 `/tools/mcp/servers` 只返回内部配置字典，不适合 UI 判断 configured/connected。
- 解决：新增 `list_server_statuses()`，统一返回 name/configured/connected/config。
- 问题：工具侧栏只显示名称和描述，缺少参数 schema。
- 解决：新增 `list_tool_details()`，从 LangChain tool 的 `args_schema` 提取 JSON schema；没有 schema 时返回 `null`。
- 问题：reload 后前端需要看到结果，而不仅是状态码。
- 解决：reload API 返回 server 状态和 MCP 工具详情，前端直接刷新展示。

**验证**：
- `ReadLints` 检查 MCP 后端、测试、前端组件与样式文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase15_mcp.py -q` → 1 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-CxlXWF6T.js 385.68KB`、`index-D8PBYBJm.css 22.54KB`。

### [Phase 15.2] 插件治理闭环 — 已完成

**实现思路**：原插件系统已有安全默认加载器：扫描 `plugins_ext/*/manifest.json`，仅加载 `enabled_plugins` 中的插件；前端只能列表和 reload。本次补齐运行期治理能力：后端新增插件安装、单插件详情、启用/停用接口；启停通过更新进程内 `settings.enabled_plugins` 后重新加载插件，加载失败不会中断其他插件，而是写入该插件 `error` 字段。前端插件页新增安装表单、启停按钮、manifest 详情、工具列表和错误隔离提示。

**修改文件**：
- 修改 `backend/app/api/routes/plugins.py`：新增 `POST /plugins/install`、`GET /plugins/{name}`、`PUT /plugins/{name}/enabled`；保留 `POST /plugins/reload`。
- 修改 `backend/tests/test_phase10_plugins.py`：新增插件安装/详情/启停测试，以及加载失败错误隔离测试。
- 修改 `frontend/src/services/api.ts`：新增 `PluginDetail` 类型，以及 `fetchPluginDetail()`、`installPlugin()`、`setPluginEnabled()`。
- 修改 `frontend/src/components/PluginsManager.tsx`：新增安装表单、启停操作、详情面板、manifest JSON、工具列表和错误展示。
- 修改 `frontend/src/App.css`：新增插件安装表单布局样式。
- 修改 `docs/PROGRESS.md`：勾选 15.2 并追加本实现记录。

**核心代码变更**：
```python
def _set_enabled_plugin(name: str, enabled: bool) -> list[str]:
    names = settings.enabled_plugins_list
    if enabled and name not in names:
        names.append(name)
    if not enabled:
        names = [p for p in names if p != name]
    settings.enabled_plugins = ",".join(names)
    return names
```

```python
@router.put("/{name}/enabled")
async def set_plugin_enabled(name: str, body: PluginEnableRequest):
    target = _safe_plugin_dir(name)
    if not target.exists():
        raise HTTPException(status_code=404, detail="plugin not found")
    _set_enabled_plugin(name, body.enabled)
    reload_plugins()
    info = plugin_registry.get(name)
    return info.to_dict()
```

**问题与解决**：
- 问题：插件启停此前依赖环境变量 `ENABLED_PLUGINS`，UI 无法操作。
- 解决：新增运行期启停接口，更新 `settings.enabled_plugins` 并立即 `reload_plugins()`，前端可直接启用/停用。
- 问题：插件加载失败可能影响治理页可用性。
- 解决：沿用 loader 的错误隔离策略，失败插件注册为 `loaded=false` 且记录 `error`，前端用“错误隔离”标识并在详情页展示错误。
- 问题：安装接口可能被路径穿越写到插件目录外。
- 解决：新增 `_safe_plugin_dir()`，目标目录必须解析在 `settings.plugins_dir` 内；安装源必须包含合法 `manifest.json` 且 manifest.name 与请求 name 一致。

**验证**：
- `ReadLints` 检查插件后端、测试、前端插件管理与样式文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase10_plugins.py -q` → 10 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-Dsm71CEO.js 381.97KB`、`index-D-CrKXul.css 22.44KB`。

### [Phase 15.1] 技能治理闭环 — 已完成

**实现思路**：原技能管理已支持列表、安装到全局池、添加到工作区、启停和按路径扫描，但前端缺少安装表单、详情页、文件查看/编辑、删除和扫描 findings 展示。本次沿用现有 `skills_system` 目录模型，不引入数据库：后端以 `pool|workspace` 作为作用域，提供技能详情、文本文件读写、删除和扫描报告接口；前端在 `SkillsManager` 中补齐安装、详情、编辑、删除、扫描详情 UI。编辑接口限定在技能目录内的文本文件，避免越权访问。

**修改文件**：
- 修改 `backend/app/api/routes/skills.py`：新增 `GET /skills/{scope}/{name}`、`GET /skills/{scope}/{name}/file`、`PUT /skills/{scope}/{name}/file`、`DELETE /skills/{scope}/{name}`、`GET /skills/{scope}/{name}/scan-report`。
- 修改 `backend/tests/test_phase4_skills.py`：新增技能治理路由测试，覆盖安装、详情、文件编辑、扫描报告、工作区删除和全局池删除。
- 修改 `frontend/src/services/api.ts`：新增 `installSkill()`、`fetchSkillDetail()`、`fetchSkillFile()`、`updateSkillFile()`、`deleteSkill()`、`fetchSkillScanReport()` 及相关类型。
- 修改 `frontend/src/components/SkillsManager.tsx`：新增安装表单、详情打开、文件列表与编辑器、删除按钮、扫描 findings 展示。
- 修改 `frontend/src/App.css`：新增技能安装表单、详情网格、文件编辑器样式。
- 修改 `docs/PROGRESS.md`：勾选 15.1 并追加本实现记录。

**核心代码变更**：
```python
def _safe_file(skill_dir: Path, rel_path: str) -> Path:
    target = (skill_dir / rel_path).resolve()
    root = skill_dir.resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="unsafe file path")
    if target.suffix.lower() not in TEXT_EXTS:
        raise HTTPException(status_code=400, detail="unsupported file type")
    return target
```

```tsx
const openDetail = async (scope: 'pool' | 'workspace', name: string) => {
  setSelected({ scope, name })
  const data = await fetchSkillDetail(scope, name, agentId)
  setDetail(data)
  setFindings(data.scan.findings)
  const first = data.files.find(f => f.is_manifest)?.path || data.files[0]?.path || 'SKILL.md'
  const file = await fetchSkillFile(scope, name, first, agentId)
  setFileContent(file.content)
}
```

**问题与解决**：
- 问题：文件编辑接口若直接接受路径，可能访问技能目录外文件。
- 解决：后端使用 `safe_skill_dir()` 和 `_safe_file()` 双重校验，限制路径必须位于技能目录内，并且只允许扫描支持的文本类型。
- 问题：工作区技能与全局池技能目录不同，但 UI 操作形态相同。
- 解决：接口统一为 `scope=pool|workspace`，workspace 额外接收 `agent_id`，前端同一套详情与编辑组件复用两种作用域。
- 问题：首次测试安装接口返回 400。
- 解决：定位为测试用例传入了源父目录，而安装接口要求 `source_dir` 直接指向包含 `SKILL.md` 的技能目录；修正测试传参后通过。

**验证**：
- `ReadLints` 检查技能后端、测试、前端技能管理与样式文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase4_skills.py -q` → 6 passed；退出阶段仍有一次 OpenTelemetry span 导出到已关闭流的已知日志，pytest 退出码为 0。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-CpHP3NGo.js 378.92KB`、`index-mYYEiLrz.css 22.30KB`。

### [Phase 14.6] 会话历史、恢复与导出 — 已完成

**实现思路**：当前聊天仅依赖 LangGraph checkpointer 的 `thread_id` 延续上下文，前端刷新后消息列表会丢失，也没有会话列表和导出入口。本次新增轻量 JSON 会话仓库，将每轮用户/助手消息按 thread 持久化到 workspace sessions 目录；同步聊天和流式聊天完成后都会写入会话。后端提供列表、详情、搜索、Markdown 导出接口；前端聊天页侧栏新增会话历史面板，支持搜索、刷新、恢复会话和导出。

**修改文件**：
- 新增 `backend/app/memory/session_store.py`：实现 `SessionStore`，支持 `record_turn()`、`list_sessions()`、`get_session()`、`export_markdown()`。
- 修改 `backend/app/api/routes/agent.py`：同步聊天和流式聊天写入会话；新增 `GET /agent/sessions`、`GET /agent/sessions/{thread_id}`、`GET /agent/sessions/{thread_id}/export`。
- 新增 `backend/tests/test_phase14_sessions.py`：覆盖会话记录、搜索列表和 Markdown 导出。
- 修改 `frontend/src/services/api.ts`：新增会话摘要/详情类型，以及 `fetchChatSessions()`、`fetchChatSession()`、`exportChatSession()`。
- 修改 `frontend/src/components/ChatPanel.tsx`：支持外部传入恢复消息；流式聊天收到 `thread_id` 后回写父组件。
- 修改 `frontend/src/App.tsx`：聊天页侧栏新增 `ChatHistoryPanel`；恢复会话时设置 `threadId`、`agentId`、`activeTraceId` 和消息列表；导出时下载 Markdown。
- 修改 `frontend/src/App.css`：新增历史面板、搜索框、历史项和侧栏堆叠样式。
- 修改 `docs/PROGRESS.md`：勾选 14.6 并追加本实现记录。

**核心代码变更**：
```python
session_store.record_turn(
    thread_id=thread_id,
    agent_id=request.agent_id or "default",
    user_message=request.message,
    assistant_message=str(result.get("response", "")),
    trace_id=str(result.get("trace_id", "")),
    run_id=str(result.get("run_id", "")),
    source=request.source,
)
```

```tsx
<ChatHistoryPanel
  onRestore={(session) => {
    setThreadId(session.thread_id)
    setAgentId(session.agent_id || 'default')
    setActiveTraceId(session.last_trace_id || null)
    setRestoredMessages(session.messages)
    setHistoryVersion(v => v + 1)
    navigate('/chat')
  }}
/>
```

**问题与解决**：
- 问题：流式聊天之前没有把新生成的 `thread_id` 回写到前端，后续消息可能无法沿用同一线程。
- 解决：`ChatPanel` 在 SSE 数据中捕获 `thread_id` 并调用 `onThreadId()`。
- 问题：流式输出没有最终 ChatResponse，无法直接拿到完整助手回复。
- 解决：后端在流式事件循环中保留最后一次可识别的 assistant content，流结束后写入会话仓库。
- 问题：需要搜索和导出，但不宜引入数据库迁移。
- 解决：先使用 JSON 文件按 thread 持久化，列表时扫描 sessions 目录并做简单全文过滤；导出时生成 Markdown。

**验证**：
- `ReadLints` 检查会话后端、前端聊天历史相关文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase14_sessions.py -q` → 1 passed。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-BlaIoOyj.js 373.97KB`、`index-D9HiJdVA.css 21.64KB`。

### [Phase 14.5] Provider 配置写入与默认模型切换 — 已完成

**实现思路**：现有 Provider 管理已能列表、查模型和检测连接，但配置仍只能依赖环境变量。本次在后端新增运行期配置接口，支持读取默认 provider/model、按 provider 写入 API Key 与 base_url、切换默认模型；前端模型设置页在保留“检测/模型”能力的基础上新增配置表单。API Key 不回显明文，只返回 `api_key_configured` 状态；表单中 API Key 留空表示不修改，避免误清空密钥。

**修改文件**：
- 修改 `backend/app/api/routes/providers.py`：新增 `GET /providers/config`、`PUT /providers/default`、`GET /providers/{name}/config`、`PUT /providers/{name}/config`。
- 修改 `backend/tests/test_phase6_providers.py`：新增 Provider 运行期配置接口测试。
- 修改 `frontend/src/services/api.ts`：新增 `ProviderConfig`、`DefaultProviderConfig` 类型，以及 `fetchDefaultProviderConfig()`、`updateDefaultProvider()`、`fetchProviderConfig()`、`updateProviderConfig()`。
- 修改 `frontend/src/components/ProviderSettings.tsx`：新增 API Key/base_url/default model 表单；支持保存 provider 配置、设为默认模型、展示当前默认模型。
- 修改 `docs/PROGRESS.md`：勾选 14.5 并追加本实现记录。

**核心代码变更**：
```python
@router.put("/{name}/config")
async def update_provider_config(name: str, body: ProviderConfigUpdate):
    provider_manager.get(name)
    if name == "openai":
        if body.api_key is not None:
            settings.openai_api_key = body.api_key
        if body.base_url is not None:
            settings.openai_base_url = body.base_url
    ...
    return _provider_config(name)
```

```tsx
const payload: { api_key?: string; base_url?: string } = { base_url: baseUrl }
if (apiKey.trim()) payload.api_key = apiKey.trim()
const cfg = await updateProviderConfig(selected, payload)
```

**问题与解决**：
- 问题：API Key 不能明文回显，否则会把敏感信息暴露到前端状态和页面。
- 解决：后端只返回 `api_key_configured` 布尔值；前端输入框使用“已配置；留空不修改”的提示，不展示原始密钥。
- 问题：不同 provider 的字段不同，`ollama` 不需要 API Key。
- 解决：后端按 provider 分支更新字段；前端在选择 `ollama` 时禁用 API Key 输入，只保留 base_url 与默认模型配置。
- 问题：本次配置写入是运行期更新，尚未持久化 `.env`。
- 解决：先完成产品管理闭环的运行期可配置能力，并在记录中明确持久化可作为后续增强；当前接口会立即影响 provider `is_configured()` 与模型创建时使用的 settings。

**验证**：
- `ReadLints` 检查 `ProviderSettings.tsx`、`api.ts`、`providers.py`、`test_phase6_providers.py` → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase6_providers.py -q` → 9 passed；退出阶段出现一次 OpenTelemetry span 导出到已关闭流的异常日志，pytest 退出码为 0，未影响测试结论。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-DF4_pxRv.js 371.40KB`、`index-DmhVOAJ-.css 20.38KB`。

### [Phase 14.4] 安全设置页与审批历史 — 已完成

**实现思路**：原有安全能力已有 ToolGuard 配置读写接口和待审批列表，但前端只在侧栏展示 `ApprovalCard`，缺少可配置策略和可追溯历史。本次最小补齐闭环：后端 `ApprovalService` 增加全量审批记录查询，安全路由新增 `/security/approvals/history`；前端安全设置页读取/更新 Guard level，展示待审批卡片，并列出审批历史。现有 `/security/approvals` 和 `/security/approvals/resume` 行为保持不变，避免影响已有审批流程。

**修改文件**：
- 修改 `backend/app/security/approval.py`：新增 `ApprovalService.list_all()`，按创建时间倒序返回全部审批请求。
- 修改 `backend/app/api/routes/security.py`：新增 `GET /api/v1/security/approvals/history`。
- 修改 `backend/tests/test_phase3_security.py`：新增审批历史包含已处理请求的单测。
- 修改 `frontend/src/services/api.ts`：新增 `fetchApprovalHistory()`、`updateGuardConfig(level)`。
- 修改 `frontend/src/App.tsx`：新增 `SecuritySettings`，安全 Tab 支持 Guard level 选择、待审批展示、审批历史刷新。
- 修改 `frontend/src/App.css`：新增安全配置卡片和审批历史列表样式。
- 修改 `docs/PROGRESS.md`：勾选 14.4 并追加本实现记录。

**核心代码变更**：
```python
def list_all(self) -> list[ApprovalRequest]:
    return sorted(self._requests.values(), key=lambda r: r.created_at, reverse=True)

@router.get("/approvals/history")
async def list_approval_history():
    return {"approvals": [r.to_dict() for r in approval_service.list_all()]}
```

```ts
export async function updateGuardConfig(level: string): Promise<{ enabled: boolean; level: string }> {
  const res = await fetch(`${API_BASE}/security/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
```

**问题与解决**：
- 问题：审批历史没有后端接口，前端只能看到 pending，已批准/拒绝后不可追踪。
- 解决：在现有内存 `ApprovalService` 上增加 `list_all()` 与 history 路由，先满足运行期审计；持久化历史可在后续存储演进中迁移到 SQLite/JSONL。
- 问题：不能破坏现有 `ApprovalCard` 的 pending 轮询与 resume 流程。
- 解决：新增接口不改变 `/approvals` 响应结构，安全页继续复用 `ApprovalCard` 展示待审批。
- 问题：Guard 配置只能读，无法在 UI 修改。
- 解决：前端新增 `updateGuardConfig(level)` 调用现有 `PUT /security/config`，通过下拉框切换 strict/smart/auto/off。

**验证**：
- `ReadLints` 检查前端、后端安全相关文件 → 无诊断。
- `cd backend && .venv\Scripts\python -m pytest tests\test_phase3_security.py -q` → 10 passed。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-BKG005JG.js 368.81KB`、`index-DmhVOAJ-.css 20.38KB`。

### [Phase 14.3] Agent 工作区详情页 — 已完成

**实现思路**：在 14.1 的 `/agents` 路由基础上，将 Agent 页面从简单列表增强为“列表 + 详情”双栏工作区视图。后端当前已提供 `GET /agents`、`GET /agents/{agent_id}`、`DELETE /agents/{agent_id}`，因此本次接入真实详情和删除能力；对于运行历史和文件索引，当前后端没有按 Agent 查询的专用接口，本次不伪造数据，而是在详情页展示 workspace root、files root 和明确的待接入说明，同时聚合嵌入 `SkillsManager` 展示该 Agent 的技能状态。

**修改文件**：
- 修改 `frontend/src/services/api.ts`：新增 `fetchAgent(agentId)`，复用已有 `deleteAgent(agentId)`。
- 修改 `frontend/src/App.tsx`：路由解析支持 `/agents/:agentId`；增强 `AgentsPage`，支持加载选中 Agent 详情、列表选择、设为当前、删除非 default Agent、展示 root/files/config/created_at/loaded/skills_count，并内嵌 `SkillsManager agentId={selected.agent_id}`。
- 修改 `frontend/src/App.css`：新增 `agent-workspace-grid`、`agent-detail-card`、`agent-summary-grid` 等布局样式。
- 修改 `docs/PROGRESS.md`：勾选 14.3 并追加本实现记录。

**核心代码变更**：
```ts
export async function fetchAgent(agentId: string): Promise<AgentInfo> {
  const res = await fetch(`${API_BASE}/agents/${agentId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
```

```tsx
if (path.startsWith('/agents/')) {
  return { page: 'agents', agentId: decodeURIComponent(path.slice('/agents/'.length)) }
}
```

```tsx
<SkillsManager agentId={selected.agent_id} />
<div className="security-hint">
  当前后端尚未提供按 Agent 查询运行历史或文件列表的索引接口。本页已展示工作区根目录与 files 路径，后续可在此处接入运行历史和文件浏览 API。
</div>
```

> 现状更新：该占位能力已在 Phase 17.1 补齐，当前 `/agents/:agentId` 已接入运行历史与 files 目录索引。

**问题与解决**：
- 问题：`default` Agent 不允许删除，后端会返回 400。
- 解决：前端在详情页对 `default` 禁用删除按钮，避免误操作；非默认 Agent 删除前使用 `window.confirm` 二次确认。
- 问题：运行历史和文件列表并没有后端索引接口，直接做假数据会造成记录不可信。
- 解决：页面展示真实 `root` 与推导的 `files` 路径，并明确说明运行历史/文件索引待后续 API 接入；技能聚合则用已存在的 `SkillsManager` 真实查询当前 Agent 技能。
- 问题：工作区路径可能来自 Windows 或 POSIX。
- 解决：拼接 files root 时同时兼容 `/` 与 `\` 结尾，避免产生重复或错误分隔符。

**验证**：
- `ReadLints` 检查 `App.tsx`、`App.css`、`api.ts` → 无诊断。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-DjHnGsYo.js 366.53KB`、`index-cQOma0AO.css 19.47KB`。

### [Phase 14.2] 任务生命周期 UI — 已完成

**实现思路**：后端已经具备任务列表、单任务详情、重跑和取消接口，但前端此前只支持创建和查看列表。本次在 14.1 路由基础上补齐任务生命周期入口：任务列表支持状态筛选，任务点击后进入 `/tasks/:taskId` 深链详情页；详情页可调用后端重跑/取消接口，并可跳转关联 Trace。聊天页侧栏中点击任务仍保留弹窗体验，弹窗与路由详情共用同一套详情内容和操作逻辑。

**修改文件**：
- 修改 `frontend/src/services/api.ts`：`fetchTasks(status?)` 支持状态查询；新增 `fetchTask(taskId)`、`runTask(taskId)`、`cancelTask(taskId)`。
- 修改 `frontend/src/components/TaskMonitor.tsx`：新增状态筛选下拉；按筛选值调用 `fetchTasks(status)`；轮询与手动刷新保持原行为。
- 修改 `frontend/src/components/TaskMonitor.css`：新增状态筛选、危险按钮、禁用按钮样式。
- 修改 `frontend/src/App.tsx`：路由解析支持 `/tasks/:taskId`；新增 `TaskDetailPanel`、`TaskDetailContent`；任务详情支持重跑、取消、Trace 跳转；任务页点击任务进入深链。
- 修改 `frontend/src/App.css`：新增任务详情卡片、操作区、错误提示样式。
- 修改 `docs/PROGRESS.md`：勾选 14.2 并追加本实现记录。

**核心代码变更**：
```ts
export async function fetchTasks(status?: string): Promise<Task[]> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
  const res = await fetch(`${API_BASE}/tasks${suffix}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function runTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/tasks/${taskId}/run`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
```

```tsx
if (path.startsWith('/tasks/')) {
  return { page: 'tasks', taskId: decodeURIComponent(path.slice('/tasks/'.length)) }
}
```

```tsx
<TaskDetailPanel
  taskId={route.taskId}
  onTrace={(traceId) => {
    setActiveTraceId(traceId)
    navigate(`/trace/${traceId}`)
  }}
/>
```

**问题与解决**：
- 问题：任务页需要深链详情，但原 `TaskMonitor` 只通过回调打开全局弹窗。
- 解决：在 `App` 的任务路由下根据当前页面判断点击行为：任务页点击进入 `/tasks/:taskId`，聊天侧栏点击继续打开弹窗。
- 问题：重跑/取消后需要立即反映最新状态。
- 解决：`TaskDetailContent` 调用 `runTask`/`cancelTask` 后把返回的 `Task` 回写到详情状态和 `selectedTask`，无需等待下一次轮询。
- 问题：Trace 跳转需要同时更新全局 activeTraceId 与 URL。
- 解决：详情组件通过 `onTrace` 回调统一设置 `activeTraceId` 并导航到 `/trace/:traceId`。

**验证**：
- `ReadLints` 检查 `App.tsx`、`App.css`、`TaskMonitor.tsx`、`TaskMonitor.css`、`api.ts` → 无诊断。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-cy4VxRGC.js 363.43KB`、`index-DlxtO5au.css 19.16KB`。

### [Phase 14.1] 页面级路由与导航入口 — 已完成

**实现思路**：在不引入新依赖的前提下，用浏览器 History API 为现有 React 单页控制台补一层轻量路由。路由层识别开发态根路径和后端静态挂载路径 `/ui/*`，将原本只能靠组件状态进入的聊天、任务、Agent、Trace、设置页映射到可直达 URL。为了避免空壳页面，本次复用现有 `ChatPanel`、`TaskMonitor`、`SidePanel`、`AgentSwitcher`、`SkillsManager`、`ProviderSettings`、`CronManager`、`PluginsManager`、`ApprovalCard` 作为各页面实际内容；后续 14.2-14.6 再补各页面的完整生命周期操作。

**修改文件**：
- 修改 `frontend/src/App.tsx`：新增路由解析、导航函数、顶部导航、按 route 渲染不同页面；新增 `AgentsPage`、`SettingsPage`、`PageHeader` 内部组件；支持 `/chat`、`/tasks`、`/agents`、`/trace`、`/trace/:traceId`、`/settings/skills`、`/settings/providers`、`/settings/scheduler`、`/settings/plugins`、`/settings/security`。
- 修改 `frontend/src/App.css`：新增顶部导航、route 页面容器、route 卡片、设置页 Tab、Agent 列表、安全提示等样式；补移动端导航换行和 route grid 自适应。
- 修改 `docs/PROGRESS.md`：勾选 14.1 并追加本实现记录。

**核心代码变更**：
```tsx
function parseRoute(pathname = window.location.pathname): AppRoute {
  const path = stripUiBase(pathname).replace(/\/+$/, '') || '/'
  if (path === '/' || path === '/chat') return { page: 'chat' }
  if (path === '/tasks') return { page: 'tasks' }
  if (path === '/agents') return { page: 'agents' }
  if (path.startsWith('/trace/')) {
    return { page: 'trace', traceId: decodeURIComponent(path.slice('/trace/'.length)) }
  }
  if (path.startsWith('/settings/')) {
    return { page: 'settings', settingsTab: ... }
  }
  return { page: 'not-found' }
}
```

```tsx
const navigate = (path: string) => {
  const next = `${currentBasePath()}${path}`
  window.history.pushState({}, '', next)
  setRoute(parseRoute(next))
}
```

**问题与解决**：
- 问题：项目当前没有 `react-router`，直接引入会增加依赖与迁移面。
- 解决：先实现轻量 History API 路由，满足 URL 直达、浏览器前进后退和 `/ui/*` 部署路径识别；后续如页面复杂度上升再评估迁移到路由库。
- 问题：后端静态 UI 挂载在 `/ui/`，开发态又是 `/`，路由解析容易把 `/ui/tasks` 当成未知页。
- 解决：新增 `stripUiBase()` 和 `currentBasePath()`，解析时剥离 `/ui`，导航时自动保留当前 base。
- 问题：14.1 只做路由可能变成空壳页面。
- 解决：所有路由均挂载现有真实组件，`/tasks` 可看任务和追踪，`/agents` 可看/切换工作区，`/settings/*` 可直达技能、模型、调度、插件、安全入口。

**验证**：
- `ReadLints` 检查 `frontend/src/App.tsx`、`frontend/src/App.css` → 无诊断。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功，产物 `index-Y_eA85On.js 360.41KB`、`index-DTXxS8fs.css 18.58KB`。

### [文档闭环] 功能清单审计与计划/落实记录修订 — 已完成

**实现思路**：根据 `boetclaw-feature-inventory.canvas.tsx` 的最新审计结果，对原计划文档和落实记录进行双口径修正：保留 Phase 0-13 的代码/API 已交付事实，同时明确报告指出的产品页面与业务闭环缺口，新增 Phase 14-16 作为后续闭环路径。重点修正“前端控制台扩展已完成”与“页面路由/生命周期闭环未完成”之间的口径冲突。

**修改文件**：
- 修改 `docs/IMPLEMENTATION_PLAN.md`：升级为 v3；新增审计口径、实现基线评估、当前页面与路由边界、Phase 14-16、修正总验收、API 契约、持久化与前端路由说明。
- 修改 `docs/PROGRESS.md`：新增审计口径说明、Phase 14-16 待办、当前功能闭环状态、本记录。

**核心变更**：
- 将当前前端状态明确为“单页 React 控制台，无独立客户端路由”；页面入口为 `/` 或 `/ui/`，业务能力主要经 `/api/v1/*` 暴露。
- 将 9 个“部分接通”模块转为后续闭环任务：任务、Agent、技能、Provider、定时、安全、插件、产物、MCP。
- 将 12 类缺口归并进 Phase 14-16：产品路由与管理闭环、扩展治理与运维闭环、钻井领域数据与产物中心。

**问题与解决**：
- 问题：原 `PROGRESS.md` 以阶段代码完成为口径，容易误读为产品闭环已全部完成。
- 解决：新增“代码/API 交付”和“产品/页面闭环”双口径说明，保留已完成阶段记录，同时把未闭环项转入新阶段。
- 问题：原 `IMPLEMENTATION_PLAN.md` 部分 API 契约与当前代码不一致，如审批恢复实际为 `/security/approvals/resume`，技能 reload 未实现，任务 run/cancel 后端存在但前端未接。
- 解决：按当前代码路由修正 API 表，并将未实现或未接 UI 的项标注为 Phase 14-16。

**验证**：静态对照 `frontend/src/App.tsx`、`frontend/src/services/api.ts`、主要 React 组件、`backend/app/main.py` 与 `backend/app/api/routes/*`，确保文档路由和功能状态与代码一致。

### [Phase 13.6] 启动环境保护 — 已完成

**实现思路**：用户使用系统 Python 3.14 直接运行 `python run.py`，导致依赖从全局 site-packages 加载，并出现 `structlog` 缺失与 LangChain/Pydantic Python 3.14 兼容性警告。本次将 `run.py` 的 `uvicorn` 与 `settings` 导入下沉到预检之后，先检查 Python 版本（3.11-3.13）与关键依赖是否存在；不满足时输出明确修复命令并退出。安装脚本也增加 Python 版本检查，防止用 3.14 创建 `.venv`。

**修改文件**：
- 修改 `backend/run.py`：新增 `_preflight()`；检查 Python 版本、`uvicorn`/`fastapi`/`structlog`/`deepagents`/`langchain`/`pydantic_settings` 等关键依赖。
- 修改 `scripts/install.ps1`、`scripts/install.sh`：创建 venv 前检查 Python 3.11-3.13。
- 修改 `README.md`、`docs/DEPLOYMENT.md`：明确后端建议 Python 3.11-3.13，并用 `.venv` 启动命令。
- 修改 `docs/IMPLEMENTATION_PLAN.md`：版本要求从 `Python 3.11+` 修正为 `Python 3.11-3.13`。
- 修改 `docs/PROGRESS.md`：新增 13.6 清单与本记录。

**核心变更**：
```python
if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
    print("BoetClaw backend 需要 Python 3.11-3.13。", file=sys.stderr)
    raise SystemExit(1)

missing = [name for name in (...) if importlib.util.find_spec(name) is None]
```

**问题与解决**：
- 问题：`run.py` 顶层导入 `uvicorn` 和 `settings`，缺依赖时无法给出项目级提示。
- 解决：将导入移动到 `_preflight()` 之后，先完成版本和依赖检查。
- 问题：安装脚本可能使用系统 Python 3.14 创建不兼容 `.venv`。
- 解决：脚本创建虚拟环境前执行版本检查，不符合即退出并提示安装 3.12/3.13。

**验证**：
- `python run.py`（系统 Python 3.14）→ 快速退出并提示 Python 3.11-3.13 与 `.venv` 启动命令。
- `.venv\Scripts\python -m py_compile run.py` → 通过。
- `.venv\Scripts\python -m pytest tests\test_phase6_providers.py tests\test_phase2_plan.py -q` → 13 passed。
- `.venv\Scripts\python -m pytest -q` → 72 passed。
- `ReadLints` 检查 `run.py` 与安装脚本 → 无诊断。

### [Phase 6.8] Provider base_url 配置 — 已完成

**实现思路**：用户提出“模型可以配置 base_url，可以接入本地模型”。本次按最小兼容路径增强 Provider：为 OpenAI-compatible 本地模型服务增加 `OPENAI_BASE_URL`，可接入 vLLM、LM Studio、LocalAI、Ollama `/v1` 等；同时为 Anthropic 协议代理增加 `ANTHROPIC_BASE_URL`。当只配置 base_url 而没有真实 API Key 时，Provider 使用 `not-needed` 作为兼容服务占位 key，避免 LangChain 构造模型时缺少 key。

**修改文件**：
- 修改 `backend/app/core/config.py`：新增 `openai_base_url`、`anthropic_base_url`。
- 修改 `backend/app/providers/openai_provider.py`：`is_configured` 支持 `OPENAI_BASE_URL`；`ChatOpenAI` 传入 `base_url` 和占位 key。
- 修改 `backend/app/providers/anthropic_provider.py`：`is_configured` 支持 `ANTHROPIC_BASE_URL`；`ChatAnthropic` 传入 `base_url` 和占位 key。
- 修改 `backend/.env.example`：新增 `OPENAI_BASE_URL`、`ANTHROPIC_BASE_URL`。
- 修改 `README.md`、`docs/DEPLOYMENT.md`：补充 OpenAI-compatible 本地模型接入示例。
- 修改 `backend/tests/test_phase6_providers.py`：新增 base_url 行为测试。
- 修改 `docs/PROGRESS.md`：新增 Phase 6.8 清单与本记录。

**核心变更**：
```python
def is_configured(self) -> bool:
    return bool(settings.openai_api_key or settings.openai_base_url)

init_kwargs = {
    "model": model,
    "api_key": settings.openai_api_key or ("not-needed" if settings.openai_base_url else None),
}
if settings.openai_base_url:
    init_kwargs["base_url"] = settings.openai_base_url
```

**问题与解决**：
- 问题：本地 OpenAI-compatible 服务通常不需要真实 key，但 LangChain/OpenAI 客户端仍要求传入 `api_key`。
- 解决：当 `OPENAI_BASE_URL` 存在且 `OPENAI_API_KEY` 为空时自动使用 `not-needed` 占位，兼容本地服务。
- 问题：不能破坏原有云端 OpenAI/Anthropic 配置。
- 解决：只有 base_url 非空才传 `base_url`；已有 API Key 优先保留；测试覆盖无 key 但有 base_url 的本地模型路径。

**验证**：
- `pytest tests/test_phase6_providers.py -q` → 8 passed。
- `pytest -q` → 72 passed。
- `ReadLints` 检查配置、Provider 与测试文件 → 无诊断。

### [Phase 2.5] interrupt→confirm 联调补齐 — 已完成

**实现思路**：原清单中 Phase 2.5 仍标记为 `[~]`，原因是完整 LLM 规划往返依赖模型 Key。为避免进度长期半完成，本次补充一个不依赖真实 LLM 的 fake-agent 自动化联调：将 `AgentManager._agent` 替换为具备 `ainvoke` 的假图对象，首次 `/plan` 调用返回 `__interrupt__` 和 todos，随后调用 `confirm_plan(thread_id, "approve")`，验证传入 LangGraph `Command(resume=...)` 并沿用同一 `thread_id`。

**修改文件**：
- 修改 `backend/tests/test_phase2_plan.py`：新增 `test_plan_interrupt_confirm_roundtrip_without_llm`。
- 修改 `docs/PROGRESS.md`：将 Phase 2.5 从 `[~]` 改为 `[x]`，并补充本记录。

**核心变更**：
```python
first = await manager.invoke("/plan 生成日报", "thread-1")
assert first["interrupted"] is True

resumed = await manager.confirm_plan("thread-1", "approve")
assert isinstance(fake.calls[1][0], Command)
assert fake.calls[1][1]["configurable"]["thread_id"] == "thread-1"
```

**问题与解决**：
- 问题：真实 DeepAgents + LLM 的 interrupt 往返在 CI/本地无 API Key 时不可稳定自动化。
- 解决：验证系统边界契约而非模型输出：`/plan` 必须设置 `plan_phase="planning"` 并识别 `__interrupt__`；`confirm_plan` 必须使用 `Command(resume=decision)` 和相同 `thread_id` 恢复。这覆盖 API/frontend 所依赖的关键行为。

**验证**：`pytest -q` → 70 passed。

### [Phase 13] 部署与文档 — 已完成

**实现思路**：按最终产品化交付补齐部署与文档闭环。Dockerfile 改为三阶段构建：`frontend-build` 负责编译 React，`backend-runtime` 负责 FastAPI/DeepAgents 并复制前端 dist 到 `/ui`，`frontend-runtime` 使用 Nginx 独立托管前端并代理 `/api` 到 backend。Compose 默认启动 backend + frontend，可通过 profile 启用 Ollama。安装脚本保持零配置原则：创建 venv、安装依赖、缺失时复制 `.env.example`。文档覆盖架构、API、渠道、安全、部署，README 改为最终入口。

**修改文件**：
- 修改 `Dockerfile`：新增 `frontend-build`、`backend-runtime`、`frontend-runtime` 三阶段；backend 镜像内置 `/app/frontend_dist`；增加 healthcheck。
- 修改 `docker-compose.yml`：backend 使用 `backend-runtime` target；frontend 使用 `frontend-runtime` target；增加可选 `ollama` profile；`env_file` 先读 `.env.example`，再可选覆盖 `.env`。
- 新增 `.dockerignore`：排除 `.venv`、`node_modules`、`dist`、workspace 缓存、`.env`。
- 新增 `deploy/nginx.conf`：静态前端 + `/api`、`/docs`、`/openapi.json` 代理。
- 修改 `backend/app/main.py`：若存在 `frontend_dist`，挂载 `/ui` 静态前端，根接口返回 `ui` 地址。
- 新增 `scripts/install.ps1`、`scripts/install.sh`。
- 重写 `README.md`：最终架构、快速开始、Docker、配置、API、渠道、项目结构、文档索引。
- 新增 `docs/ARCHITECTURE.md`、`docs/API.md`、`docs/CHANNELS.md`、`docs/SECURITY.md`、`docs/DEPLOYMENT.md`。

**核心变更**：
```dockerfile
FROM node:20-alpine AS frontend-build
RUN npm ci && npm run build

FROM python:3.12-slim AS backend-runtime
COPY --from=frontend-build /src/frontend/dist /app/frontend_dist

FROM nginx:1.27-alpine AS frontend-runtime
COPY --from=frontend-build /src/frontend/dist /usr/share/nginx/html
```

```yaml
env_file:
  - path: backend/.env.example
  - path: backend/.env
    required: false
```

**问题与解决**：
- 问题：新克隆仓库没有 `backend/.env` 时 `docker compose config` 直接失败。
- 解决：Compose 改为先加载 `.env.example`，再可选加载 `.env` 覆盖，保证零配置可解析，同时仍支持真实配置覆盖。
- 问题：单容器后端镜像包含前端 dist 但原 FastAPI 未提供静态入口。
- 解决：`main.py` 检测 `frontend_dist` 存在时挂载 `/ui`，不影响 API 与 `/docs`。
- 问题：前端独立容器使用 Nginx 静态服务时 `/api/v1/*` 会打到前端域名。
- 解决：`deploy/nginx.conf` 将 `/api/` 代理到 `backend:8000`。

**验证**：
- `cd backend && .venv\Scripts\python -m pytest -q` → 69 passed。
- `cd frontend && npm run build` → `tsc -b && vite build` 成功。
- `docker compose config` → 通过（无需预先创建 `backend/.env`）。
- `ReadLints` 检查 `backend/app/main.py` → 无诊断。

### [Phase 12] 可观测性强化 — 已完成

**实现思路**：补齐链路可观测三件套：(1) OpenTelemetry 注入 FastAPI，HTTP 中间件将 `X-Trace-Id` 写入 `trace_id_var` 并作为 span attribute `boetclaw.trace_id` 关联；(2) `TraceStore` 事件追加落盘 JSONL，启动时加载近期记录，重启不丢链路；(3) `build_timeline` 将同一 trace 的事件按时间排序并归类（plan/guard/tool/subagent/thinking/agent/scheduler/memory…），暴露 `GET /monitor/trace/{id}/timeline`。LangSmith 沿用 Phase 1 已有 `setup_env()` 逻辑，无需额外代码。

**修改文件**：
- 新增 `core/otel.py`：`setup_otel(app)`（TracerProvider + FastAPIInstrumentor + trace 中间件），幂等/可关闭（`OTEL_ENABLED`）。
- 新增 `core/timeline.py`：`categorize`/`_summarize`/`build_timeline`。
- 修改 `core/observability.py`：`TraceStore` 增加线程锁 + `_load_from_disk`/`_append_to_disk`（JSONL）。
- 修改 `core/config.py`：`otel_enabled`、`trace_persist_enabled`、`trace_persist_max_lines`。
- 修改 `api/routes/monitor.py`：新增 `GET /trace/{trace_id}/timeline`。
- 修改 `main.py`：应用创建后调用 `setup_otel(app)`。
- 修改 `.env.example`：Observability 配置项。
- 新增 `tests/test_phase12_observability.py`。

**核心变更**：
```python
# HTTP 中间件：span 关联 trace_id
span.set_attribute("boetclaw.trace_id", tid)
response.headers["X-Trace-Id"] = tid
# TraceStore 落盘
with self._persist_path.open("a") as f:
    f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
# 时间线 API
return {"trace_id": trace_id, "categories": {...}, "events": [...]}
```

**问题与解决**：
- 问题：重复调用 `setup_otel` 或 TestClient 启动后再注册中间件会抛 `Cannot add middleware after an application has started`。
- 解决：`_instrumented` + `_middleware_registered` 双标志幂等；TracerProvider 仅在非 SDK 实例时创建；单测改为验证「已初始化后二次调用 no-op」而非重置后重入。
- 问题：全局 `trace_store` 在 import 时即加载磁盘，测试间可能污染。
- 解决：持久化/时间线单测使用独立 `TraceStore(persist_path=tmp)` 或 monkeypatch `timeline.trace_store`；API 测试用唯一 trace_id。

**验证**：`pytest -q` → 69 passed。JSONL 写盘后重载可读；timeline 含 plan/guard/tool 分类；timeline API 404/200 正确；OTel 初始化幂等。

### [Phase 11] 前端控制台扩展 — 已完成

**实现思路**：在既有 React 深色控制台基础上补齐后端 Phase 4-10 能力的可视化交互，覆盖 G9 六类：Agent 切换、Plan 确认、工具审批、技能管理、模型设置、定时/心跳、插件。为不破坏现有三栏布局，管理页集中到「控制台」模态框（Tab 切换），HITL 交互（PlanConfirm/ApprovalCard）就近嵌入对话流与侧栏。所有新 API 封装集中在 `services/api.ts`，TypeScript 严格模式类型完整。

**修改文件**：
- 修改 `services/api.ts`：新增 `ChatResult`/`confirmPlan`、agents/skills/providers/cron/security/plugins/commands 全部接口与类型，`sendChat` 增加 `agentId`。
- 新增 `components/Console.css`：模态框/Tab/列表/开关/pill/plan-confirm/approval/agent-switcher 样式。
- 新增 `AgentSwitcher.tsx`：顶栏下拉切换 + 新建 Agent，外点关闭。
- 新增 `ConsoleModal.tsx`：4 Tab（技能/模型/定时心跳/插件）容器。
- 新增 `SkillsManager.tsx`、`ProviderSettings.tsx`、`CronManager.tsx`、`PluginsManager.tsx`。
- 新增 `PlanConfirm.tsx`（todos 展示 + 批准/拒绝调 confirm API）、`ApprovalCard.tsx`（5s 轮询 pending + findings + resume）。
- 修改 `ChatPanel.tsx`：接收 `agentId`；`/plan` 或非默认 Agent 强制走非流式以获取 `interrupted`/`todos`；渲染 PlanConfirm。
- 修改 `App.tsx`：`agentId`/`consoleOpen` 状态、顶栏 AgentSwitcher + 控制台按钮、侧栏挂 ApprovalCard、挂载 ConsoleModal。
- 修改 `SidePanel.tsx`：事件按类别着色 + 中文类别标签（安全/规划/工具/子智能体/调度/网关/技能/记忆）。

**核心变更**：
```tsx
// ChatPanel：plan/多 Agent 强制非流式，拿到结构化 interrupted
const forceSync = text.startsWith('/plan') || agentId !== 'default'
if (result.interrupted) setPlanPending({ threadId: result.thread_id, todos: result.todos })
// PlanConfirm：批准/拒绝
const result = await confirmPlan(threadId, decision)
```

**问题与解决**：
- 问题：SSE 流式路径不暴露 `interrupted`/`todos`/agent 路由，Plan 门控无法闭环。
- 解决：`/plan` 或非默认 Agent 时 `forceSync` 切非流式 `sendChat`，据 `interrupted` 弹 PlanConfirm。
- 问题：TS 严格模式下 `sendChat` 返回 any 会报错。
- 解决：定义 `ChatResult` 接口，所有接口函数标注返回类型，`npm run build`（`tsc -b`）0 错误。
- 问题：Console.css 类需全局可用（AgentSwitcher/ApprovalCard 在模态外使用）。
- 解决：`App` 顶层 import ConsoleModal → Console.css 随包加载，全局类始终可用。

**验证**：`npm run build` → `tsc -b && vite build` 成功，产物 `index.js 355KB`（gzip 108KB）、`index.css 15.7KB`，0 TS 错误、0 lint 错误。六类管理页 + plan/approval HITL 闭环 + 追踪面板分类可用。

### [Phase 10] 插件系统 + 魔法命令 — 已完成

**实现思路**：对标 QwenPaw 插件机制与安全默认。插件放于 `plugins_ext/<name>/`（`manifest.json` + `plugin.py`），loader 扫描全部并注册元信息，但**仅当插件名在 `ENABLED_PLUGINS` 中才动态 import 并加载其工具**（磁盘存在≠启用，安全默认）。工具经模块 `__all__` 自动发现（具备 `.name`+`.invoke` 的 langchain tool）。魔法命令 `/new /clear /stop /restart /help /plan` 在 chat 路由前置解析，控制类命令直接返回不进 LLM；`/plan` 标记 pass_through 交由 PlanGate 处理。

**修改文件**：
- 新增 `plugins/architecture.py`：`PluginType`、`PluginManifest`（from_dict 容错）、`PluginInfo`。
- 新增 `plugins/registry.py`：`PluginRegistry`（add/list/enabled_tools，仅 enabled+loaded 注册工具）。
- 新增 `plugins/loader.py`：`discover_and_load`（扫描/条件加载/_collect_tools via __all__）、`reload_plugins`。
- 新增 `commands/registry.py`：`Command`/`CommandResult`/`CommandRegistry`（parse/execute/6 内置命令 + reset 别名）。
- 修改 `api/routes/agent.py`：chat 前置 `command_registry.execute`，命中且非 pass_through 直接返回。
- 新增 `api/routes/plugins.py`：`/plugins`、`/plugins/reload`、`/commands`。
- 修改 `core/agent_factory.py`：工具列表追加 `plugin_registry.enabled_tools()`。
- 修改 `core/startup.py`：phase1 `discover_and_load()`。
- 修改 `config.py`：`enabled_plugins`、`plugins_dir`、`enabled_plugins_list`；`.env.example` 增 `ENABLED_PLUGINS`。
- 新增示例插件 `plugins_ext/example_echo/`（默认不启用）。
- 新增 `backend/tests/test_phase10_plugins.py`。

**核心变更**：
```python
# loader：安全默认——未启用仅登记，不 import 不注册工具
is_enabled = manifest.name in enabled_names
if not is_enabled:
    plugin_registry.add(info); continue  # 不加载工具
# chat 前置：控制命令不进 LLM
cmd_result = command_registry.execute(request.message, {"thread_id": thread_id})
if cmd_result and cmd_result.handled and not cmd_result.pass_through:
    return ChatResponse(thread_id=cmd_result.new_thread_id or thread_id, ...)
```

**问题与解决**：
- 问题：动态加载磁盘上任意插件存在安全风险。
- 解决：严格「白名单启用」——仅 `ENABLED_PLUGINS` 列出的插件才 import；示例插件默认不启用，单测验证其 `echo_tool` 不进入工具集。
- 问题：`/plan` 既是命令又需走 PlanGate 规划流程。
- 解决：`/plan` 命令返回 `handled=False, pass_through=True`，chat 路由据此继续进入 agent invoke（保留既有 PlanGate 行为）。
- 问题：插件工具发现需通用且安全。
- 解决：`_collect_tools` 优先读 `__all__`，仅收集同时具备 `.name` 与 `.invoke` 的对象，避免误注册非工具符号。

**验证**：`pytest -q` → 64 passed。禁用插件不加载工具（enabled_tools 为空）、启用后 `echo_tool` 出现；`/new` 返回新 thread_id、`/help` 列出命令、`/plan` pass_through、`/reset` 别名映射 clear、未知/普通消息返回 None。

### [Phase 9] 定时任务 + 心跳 — 已完成

**实现思路**：对标 QwenPaw 自动化调度。`CronService` 内嵌 `AsyncIOScheduler`，`CronJob{id,name,cron,prompt,channel,chat_id,agent_id,enabled}` 落盘 JSON，重启可恢复。触发时以 `source="cron"` 调 agent（衔接 Phase 7：自动化来源不写长期记忆），结果按需回发指定渠道。`HeartbeatService` 按 `HEARTBEAT_INTERVAL_MINUTES` 用 `HEARTBEAT_PROMPT` 定时问 agent（`source="heartbeat"`），复用同一调度器。为可测试，两服务均支持注入 `runner`，默认回退 `agent_manager`/`multi_agent_manager`。

**修改文件**：
- 新增 `services/cron_service.py`：`CronJob`、`CronService`（_load/_persist/start/shutdown/_schedule/add_job/remove/list_jobs/_run_job/_invoke/_maybe_reply）+ 单例。
- 新增 `services/heartbeat.py`：`HeartbeatService`（config/start/_beat/_invoke/_maybe_reply）+ 单例。
- 新增 `api/routes/cron.py`：GET/POST `/tasks/cron`、DELETE `/tasks/cron/{id}`、GET/PUT `/tasks/heartbeat`。
- 修改 `api/schemas.py`：`CronJobCreateRequest`、`HeartbeatUpdateRequest`。
- 修改 `core/startup.py`：phase2 agent ready 后 `cron_service.start()` + `heartbeat_service.start(共享调度器)`。
- 修改 `main.py`：注册 cron 路由（先于 tasks，避免 `/tasks/{id}` 抢占 `/tasks/cron`），lifespan `cron_service.shutdown()`。
- 新增 `backend/tests/test_phase9_scheduler.py`。

**核心变更**：
```python
# 触发以 cron 来源调 agent（不污染记忆）
async def _run_job(self, job_id):
    emit_event(EventType.CRON_TRIGGER, {"action": "fire", "job_id": job_id})
    result = await self._invoke(job.prompt, agent_id=job.agent_id)  # source="cron"
# crontab 解析
CronTrigger.from_crontab(job.cron, timezone="UTC")
```

**问题与解决**：
- 问题：`/tasks/cron` 会被 `/tasks/{task_id}` 动态路由抢占。
- 解决：拆独立 `cron.py` 路由并在 `main.py` 中先于 tasks 注册，FastAPI 按注册顺序优先匹配静态路径。
- 问题：单测无法等待真实 cron（分钟级）触发。
- 解决：`runner` 可注入，直接调用 `_run_job` 验证触发逻辑与 `source=cron`；另用非法 crontab 验证 `from_crontab` 抛错。
- 问题：APScheduler 启动依赖运行中的事件循环。
- 解决：`start`/`shutdown` 全程 try/except，失败仅告警不影响主服务；phase2 中在 agent ready 后启动。

**验证**：`pytest -q` → 56 passed。cron 增删列 + JSON 持久化正常；`_run_job` 以 `source=cron`、`_beat` 以 `source=heartbeat` 调用；禁用/缺失任务不触发；非法 crontab 抛错。

### [Phase 8] 渠道网关抽象与扩展 — 已完成

**实现思路**：对标 QwenPaw 多渠道接入。抽象 `BaseChannel`，统一 `GatewayMessage`/`GatewayResponse` 与 `RenderStyle`（markdown/plain/card）。将原 `router.py` 单文件里的钉钉/飞书/QQ 拆分为独立 channel 模块，新增 Telegram。引入 `ChannelManager`：每渠道独立 `asyncio.Queue(maxsize=1000)` + 消费者协程，Webhook 只做解析+入队（削峰、快速响应），队列满则降级为 BackgroundTask 兜底。回发从 stub 升级为真实 API（钉钉 sessionWebhook、飞书 tenant_access_token、QQ OneBot、Telegram sendMessage），无凭据时回退 stub 事件。

**修改文件**：
- 新增 `services/gateway/base.py`：`BaseChannel(ABC)`（`channel`/`render_style`/`parse_incoming`/`send_reply`/`verify_signature`/`is_configured`，`platform` 兼容别名）、`GatewayMessage`（增 `is_group`）、`GatewayResponse`、`RenderStyle`。
- 新增 `renderer.py`：`MessageRenderer`（render/render_card/_to_plain/truncate）。
- 新增 `channels/dingtalk.py`、`feishu.py`、`qq.py`、`telegram.py`。
- 新增 `manager.py`：`ChannelManager`（register/get/enqueue/queue_size/start/stop/bootstrap_from_settings）+ 单例。
- 重写 `api/routes/gateway.py`：`default_message_handler`（run agent，source=channel，回发）+ `_handle_webhook` 通用入队 + 各平台/通用 webhook 路由。
- 修改 `core/startup.py`：phase1 注册渠道并启动消费者。
- 修改 `main.py`：移除旧 gateway_router 注册，lifespan 关停 ChannelManager。
- 修改 `config.py`：新增 `telegram_bot_token`；`.env.example` 增 Telegram/记忆配置。
- 删除旧 `services/gateway/router.py`。
- 新增 `backend/tests/test_phase8_channels.py`。

**核心变更**：
```python
# manager.enqueue：队列满降级
try: q.put_nowait(message); return True
except asyncio.QueueFull:
    emit_event(EventType.GATEWAY_MESSAGE, {"platform": name, "action": "dropped"}); return False
# webhook：入队失败回退 BackgroundTask
queued = channel_manager.enqueue(platform, message)
if not queued: background_tasks.add_task(default_message_handler, channel, message)
```

**问题与解决**：
- 问题：重构可能破坏依赖旧 `gateway_router` 的 main.py/route。
- 解决：以 `ChannelManager` 全量替换，删除旧 router.py，`BaseChannel.platform` 保留别名兼容旧字段命名；全量测试回归确认无破坏。
- 问题：真实回发在测试/无凭据环境会发起网络请求。
- 解决：回发全部 try/except + 凭据/回调地址判空回退 stub 事件；单测只覆盖解析与队列，不触发网络。
- 问题：plain 渲染的标题正则误判行内 `#`。
- 解决：`^#{1,6}\s*` 仅匹配行首标题（符合 markdown 语义），修正测试用真实标题样例。

**验证**：`pytest -q` → 50 passed。钉钉/飞书/QQ/Telegram 四渠道样例 payload 解析正确（含群聊标记）；队列超上限第 3 条被丢弃；消费者协程正确处理入队消息。

### [Phase 7] 记忆与上下文策略 — 已完成

**实现思路**：对标 QwenPaw「自动化触发不污染长期记忆」原则。为每次 invoke 增加 `source` 字段（user/channel/cron/heartbeat），`context_policy.should_persist_memory` 判定是否写长期记忆——`cron`/`heartbeat` 自动化来源跳过。记忆后端可切换 file(AGENTS.md) / store(跨线程) / none。上下文压缩复用 DeepAgents 内置 `SummarizationMiddleware`，由配置开关，构造失败（如无 API Key）时优雅降级为不启用。

**修改文件**：
- 新增 `backend/app/memory/context_policy.py`：`AUTOMATION_SKIP_SOURCES`、`normalize_source`、`should_persist_memory`、`is_automation`。
- 新增 `memory/store_backend.py`：`get_store()`（memory_backend=store 时惰性建 `InMemoryStore`）、`get_memory_files()`。
- 修改 `core/config.py`：新增 `memory_backend`、`context_summarization_enabled`、`context_keep_messages`、`context_trigger_tokens`。
- 修改 `core/observability.py`：新增 `MEMORY_PERSIST`/`MEMORY_SKIP` 事件。
- 修改 `core/agent_factory.py`：新增 `_build_summarization_mw`；`build` 增加 `enable_summarization`、`store` 参数，中间件序追加摘要中间件。
- 修改 `core/agent.py`、`agents/runtime.py`：invoke 增加 `source`，按策略发 `MEMORY_PERSIST`/`MEMORY_SKIP`，返回体含 `source`。
- 修改 `agents/multi_agent_manager.py`：`_build_agent` 用 `get_memory_files()`/`get_store()`。
- 修改 `api/schemas.py`、`api/routes/agent.py`：`ChatRequest.source` 透传。
- 新增 `backend/tests/test_phase7_memory.py`。

**核心变更**：
```python
# context_policy：自动化来源跳过长期记忆
AUTOMATION_SKIP_SOURCES = {"cron", "heartbeat"}
def should_persist_memory(source): return normalize_source(source) not in AUTOMATION_SKIP_SOURCES
# invoke 结束按策略发事件
emit_event(EventType.MEMORY_PERSIST if persist_memory else EventType.MEMORY_SKIP, {...})
```

**问题与解决**：
- 问题：`SummarizationMiddleware` 传字符串模型会触发 `init_chat_model`，无 API Key 时抛异常。
- 解决：`_build_summarization_mw` 全程 try/except，异常时告警并返回 None（优雅降级）；单测分别用 `FakeListChatModel` 验证成功路径、用字符串验证降级路径。
- 问题：Store 后端在无 langgraph store 环境不可用。
- 解决：`get_store` 仅在 `memory_backend=store` 时惰性构造并 try/except，失败回退 None。

**验证**：`pytest -q` → 41 passed。cron/heartbeat 来源 `should_persist_memory=False`；摘要中间件用假模型可构建、无 Key 字符串模型优雅降级。

### [Phase 6] Provider 抽象 + 本地模型 — 已完成

**实现思路**：将模型提供商统一到 `Provider` 抽象接口，`ProviderManager` 单例注册 OpenAI/Anthropic/Ollama 三家，通过 `provider:model` 字符串解析定位实例。所有第三方 langchain 包（`langchain_anthropic`/`langchain_ollama`）在 `get_chat_model` 内部惰性导入，保证未安装/未配置环境仍可导入与测试。能力探测结果落盘 JSON 缓存。工厂改由 `_resolve_model` 决定：provider 已配置时返回真实模型实例，否则回退 `provider:model` 字符串交由 deepagents 惰性解析，向后兼容。

**修改文件**：
- 新增 `backend/app/providers/base.py`：`ModelInfo`、`ProviderInfo`、`Provider(ABC)`（`get_chat_model`/`list_models`/`is_configured`/`check_connection`/`info`）。
- 新增 `openai_provider.py`/`anthropic_provider.py`/`ollama_provider.py`（后者含 `/api/tags` 探测已装模型 + 连通性检查）。
- 新增 `capability_cache.py`：`CapabilityCache`（线程锁 + 落盘）、`get_capability_cache()`。
- 新增 `manager.py`：`ProviderManager`（注册/获取/`parse_model_string`/`get_chat_model`/`check_connection`）+ 单例。
- 新增 `backend/app/api/routes/providers.py`：GET `/providers`、GET `/providers/{name}/models`、POST `/providers/{name}/check`。
- 修改 `core/agent_factory.py`：新增 `_resolve_model()`，`build` 的 model 默认走它。
- 修改 `main.py`：注册 providers 路由。
- 修改 `requirements.txt`：新增 `langchain-anthropic`、`langchain-ollama`。
- 新增 `backend/tests/test_phase6_providers.py`。

**核心变更**：
```python
# manager.py：provider:model 解析
if ":" in model_string:
    provider, _, model = model_string.partition(":")
    return provider.strip(), model.strip()
# agent_factory._resolve_model：已配置才实例化，否则回退字符串
if provider.is_configured():
    return provider_manager.get_chat_model(settings.model_string)
return settings.model_string
```

**问题与解决**：
- 问题：测试/CI 环境未安装 anthropic/ollama 包，也无 API Key，直接实例化会失败。
- 解决：第三方导入下沉到 `get_chat_model`；工厂 `_resolve_model` 仅在 `is_configured()` 时实例化，否则回退字符串，导入期零副作用。
- 问题：Ollama 未运行时 `/check` 与 `list_models` 会异常。
- 解决：`httpx` 请求包 try/except，超时 2s，失败返回 `connected=False` 而非抛错；单测仅断言返回结构。

**验证**：`pytest -q` → 34 passed。`parse_model_string` 正确拆分；能力缓存写盘后重载可读回；三 provider 均可枚举，Ollama `requires_api_key=False`。

### [Phase 5] 多智能体 Workspace — 已完成

**实现思路**：对标 QwenPaw 多智能体隔离能力。每个 agent 一个 `Workspace`（独立 `skills/`、`files/`、config），由 `MultiAgentManager` 懒加载构建（首次访问才 `create_deep_agent`）；用 per-agent `asyncio.Lock` + 双检锁避免并发重复构建；`FilesystemBackend(root_dir=files_dir)` 保证文件系统隔离；空闲超 TTL 驱逐 agent 实例（默认智能体常驻）。路由采用 4 级优先级：显式参数 > request.state > 请求头 > 配置默认。为避免与已有 `AgentManager.invoke` 逻辑重复，抽出 `runtime.invoke_agent/confirm_agent` 共享运行逻辑。

**修改文件**：
- 新增 `backend/app/agents/workspace.py`：`Workspace`（`skills_dir`/`files_dir`/`to_dict`）。
- 新增 `multi_agent_manager.py`：`MultiAgentManager`（`get_agent` 懒加载、`create`/`delete`/`list_agents`/`evict_idle`），`_build_agent` 复用 `BoetClawAgentFactory` + `resolve_effective_skills`。
- 新增 `agent_context.py`：`resolve_agent_id`（4 级路由）。
- 新增 `runtime.py`：`invoke_agent`/`confirm_agent` 共享运行逻辑（trace/run id、/plan 识别、interrupt 检测）。
- 新增 `backend/app/api/routes/agents.py`：GET/POST `/agents`、GET/DELETE `/agents/{id}`。
- 修改 `schemas.py`：`ChatRequest.agent_id`、`ChatResponse.agent_id`。
- 修改 `routes/agent.py`：chat 依据 `agent_id` 路由到工作区。
- 修改 `main.py`：注册 agents 路由。
- 新增 `backend/tests/test_phase5_agents.py`。

**核心变更**：
```python
# 双检锁 + to_thread 构建，避免阻塞事件循环
async with self._lock(agent_id):
    ws = self._ws.get(agent_id)
    if ws and ws.agent is not None: return ws
    ws.agent = await asyncio.to_thread(self._build_agent, ws)
# 每工作区独立文件后端
FilesystemBackend(root_dir=str(ws.files_dir()))
```

**问题与解决**：
- 问题：并发首访同一 agent 可能重复构建。
- 解决：per-agent 锁 + 进入锁后二次检查；单测用 monkeypatch 计数验证 10 并发仅构建 1 次。
- 问题：与单体 `AgentManager.invoke` 逻辑重复。
- 解决：抽 `runtime.py` 承载 invoke/confirm，工作区与后续单体可共用。
- 问题：默认智能体误删风险。
- 解决：`delete` 对 `default` 抛 `ValueError`，API 转 400。

**验证**：`pytest -q` → 28 passed。隔离测试确认 agentA 写入的文件对 agentB 不可见；4 级路由优先级正确。

### [Phase 4] 技能体系双层 — 已完成

**实现思路**：对标 QwenPaw「技能池（共享）+ 工作区技能（运行副本）」双层机制。池服务管理 `backend/skills/` 全局仓库，工作区服务按 agent 复制并维护启停状态；`resolve_effective_skills` 供 `create_deep_agent(skills=...)`；安装前经 `SkillScanner` 检测密钥与危险代码。

**修改文件**：
- 新增 `backend/app/skills_system/models.py`：`SkillInfo`、`SkillConflictError`。
- 新增 `store.py`：`get_skill_pool_dir`/`get_workspace_skills_dir`/`safe_skill_dir`（防路径穿越）/`parse_frontmatter`/`read_skill_manifest`/`list_skill_dirs`。
- 新增 `scanner.py`：`SkillScanner`（5 类密钥正则 + 6 类危险代码正则）。
- 新增 `pool_service.py`：`SkillPoolService`（list/get/install（含 scan）/remove）。
- 新增 `workspace_service.py`：`SkillService`（工作区副本、`skills_state.json` 启停、`effective_dirs`）。
- 新增 `registry.py`：`resolve_effective_skills(workspace_dir, channel)`（工作区优先，回退全局池）。
- 新增 `backend/app/api/routes/skills.py`：list/install/enable/add-to-workspace/scan。
- 修改 `backend/app/main.py`：注册 skills 路由。
- 新增内置技能 `skills/las-parser/`、`skills/hse-compliance/`。
- 新增 `backend/tests/test_phase4_skills.py`。

**核心变更**：
```python
# store.py：轻量 frontmatter 解析（key: value）
m = _FRONTMATTER_RE.match(text)  # ^---\n...\n---\n
# scanner.py：安装前拦截
if pat.search(line): findings.append(ScanFinding(...))
# registry.py：工作区优先，回退池
if ws_skills.exists() and any(ws_skills.iterdir()): dirs.append(str(ws_skills))
else: dirs.append(str(settings.skills_dir))
```

**问题与解决**：
- 问题：不引入 PyYAML 也要解析 SKILL.md frontmatter。
- 解决：用正则截取 `---...---` 块 + 逐行 `key: value` 解析，满足现有技能格式（name/description/languages）。
- 问题：安装技能存在路径穿越风险。
- 解决：`safe_skill_dir` 校验解析后路径必须位于 base 之下。

**验证**：`pytest -q` → 24 passed。扫描器正确识别 `sk-` 密钥与 `os.system` 危险代码；内置池可枚举技能。

### [Phase 3] ToolGuard 安全层 — 已完成

**实现思路**：对标 QwenPaw 的 ToolGuard，用 `ToolGuardMiddleware.wrap_tool_call` 在工具执行前经安全引擎评估。引擎聚合三个 Guardian 的 findings，按 4 级执行策略（STRICT/SMART/AUTO/OFF）决定「放行/拦截/审批」；审批走 LangGraph interrupt（复用 Phase 2 的 resume 机制）。

**修改文件**：
- 新增 `backend/app/security/execution_level.py`：`ToolExecutionLevel`、`GuardSeverity`。
- 新增 `backend/app/security/models.py`：`GuardFinding`、`GuardResult`（含 `merge`/`max_severity`）。
- 新增 `backend/app/security/guardians/{base,rule_guardian,file_guardian,shell_guardian}.py`。
- 新增 `backend/app/security/engine.py`：`ToolGuardEngine`（决策矩阵）+ 单例 `get_guard_engine`/`reload_guard_engine`。
- 新增 `backend/app/security/approval.py`：`ApprovalService` + `ApprovalRequest`。
- 新增 `backend/app/middleware/tool_guard_mw.py`：拦截中间件。
- 新增 `backend/app/api/routes/security.py`：`GET/PUT /security/config`、`GET /security/approvals`、`POST /security/approvals/resume`。
- 修改 `backend/app/core/agent_factory.py`：固定中间件顺序，新增 `enable_tool_guard`。
- 修改 `backend/app/main.py`：注册 security 路由。
- 新增 `backend/tests/test_phase3_security.py`（9 项）。

**核心变更**：
```python
# engine.py 决策矩阵（SMART：MEDIUM+ 审批；硬 deny 优先）
if not result.allowed: return result
if level == SMART: result.requires_approval = sev.value >= MEDIUM.value
```
```python
# tool_guard_mw.py：拦截 → 审批 interrupt → 放行/拒绝
if not res.allowed: return ToolMessage("[安全拦截] ...", status="error")
if res.requires_approval:
    decision = interrupt({"type":"tool_approval",...})
    if decision != "approve": return ToolMessage("[用户拒绝执行]", status="error")
```

**问题与解决**：
- 问题：`FilePathToolGuardian` 需从任意工具参数中识别路径。
- 解决：按常见键名（file_path/path/filename…）+ 含分隔符/以点开头的字符串启发式提取，命中 deny 列表即 CRITICAL 拒绝。
- 问题：中间件内拿不到 config 的 thread_id，无法用 approval_id 直接 resume。
- 解决：MVP 由前端持有 thread_id 调 `/security/approvals/resume`；`approval_service` 仅作待审可视化。后续可从 checkpoint state 读取补全。
- 问题：单测环境无图上下文，`interrupt()` 抛错。
- 解决：中间件对 interrupt 包 try/except，测试环境降级为默认 approve，仅验证「拦截」路径（不触发 interrupt）。

**验证**：`pytest -q` → 19 passed（含前序阶段）。`from app.main import app` 正常，12 路由组注册。
**决策矩阵单测**：SMART 下 generate_chart 放行、write_file 审批、写 `.env` 硬拒；OFF 全放行。

### [Phase 2] Plan 门控 + HITL — 已完成

**实现思路**：用 DeepAgents 内置 `write_todos` 作为规划工具，扩展 state 增加 `plan_phase`，通过 `PlanGateMiddleware.wrap_tool_call` 实现「规划态拦截非规划工具 + 计划生成后 interrupt 等待确认」。`/plan` 前缀进入规划态，`POST /agent/plan/confirm` 用 `Command(resume=...)` 恢复被挂起的图。

**修改文件**：
- 新增 `backend/app/agents/__init__.py`、`state.py`：`BoetClawState(DeepAgentState)` 增加 `plan_phase`。
- 新增 `backend/app/middleware/plan_gate_mw.py`：门控逻辑（planning 拦截、write_todos 触发 interrupt，interrupt 在非图上下文安全降级）。
- 修改 `backend/app/core/agent_factory.py`：`enable_plan_gate=True` 默认注入 PlanGate + `state_schema=BoetClawState`。
- 修改 `backend/app/core/agent.py`：`invoke` 识别 `/plan` 前缀→初始 state `plan_phase=planning`，返回 `interrupted` 标志；新增 `confirm_plan()`。
- 修改 `backend/app/api/schemas.py`：`ChatResponse.interrupted`、`PlanConfirmRequest`。
- 修改 `backend/app/api/routes/agent.py`：新增 `POST /agent/plan/confirm`。
- 新增 `backend/tests/test_phase2_plan.py`。

**核心变更**：
```python
# plan_gate_mw.py：规划态拦截 + 计划确认
if phase == "planning" and tool not in PLAN_TOOLS:
    return ToolMessage(content="当前处于规划阶段…", tool_call_id=..., status="error")
if tool == "write_todos":
    result = handler(request); emit(PLAN_CREATED)
    decision = interrupt({"type":"plan_confirm","todos":...}); emit(PLAN_CONFIRMED)
    return result
```
```python
# agent.py：恢复
await self.agent.ainvoke(Command(resume=decision), config)
```

**问题与解决**：
- 问题：`interrupt()` 在单元测试（无图运行时）会抛错。
- 解决：中间件对 `interrupt()` 包 try/except，非图上下文降级为 THINKING 事件，保证可单测；真实运行时正常挂起。
- 问题：`DeepAgentState` 是 dict 型 TypedDict。
- 解决：直接子类化并新增 `plan_phase`，`state.get("plan_phase","idle")` 读取。

**验证**：`pytest -q` → 10 passed。门控拦截/放行逻辑单测覆盖。
**手动验证（需 LLM Key）**：`POST /agent/chat {"message":"/plan ..."}` → 返回 `interrupted=true` → `POST /agent/plan/confirm {decision:"approve"}` 继续执行。

### [Phase 1] 核心基座 — 已完成

**实现思路**：把散落在 `agent.py` 里的构建逻辑抽到统一工厂 `BoetClawAgentFactory`，并以中间件方式注入横切能力（可观测性），为后续 Plan 门控/ToolGuard 中间件预留注入点（`extra_middleware` / `state_schema`）。同时将启动改为两阶段，让服务秒级就绪、重资源后台加载。

**修改文件**：
- 新增 `backend/app/middleware/__init__.py`、`observability_mw.py`：基于实测钩子 `before_model`/`after_model`/`wrap_tool_call` 发射 THINKING/TOOL_CALL/TOOL_RESULT 事件。
- 新增 `backend/app/core/agent_factory.py`：`setup_env()`、`build_default_subagents()`（含新增 reviewer 子智能体）、`BoetClawAgentFactory.build(...)` 统一装配中间件栈、interrupt_on、backend、checkpointer、state_schema。
- 修改 `backend/app/core/agent.py`：`initialize()` 改为调用工厂，保留对外 `invoke/stream/list_tools` 接口不变。
- 新增 `backend/app/core/startup.py`：`phase1_fast`（<1s 就绪）+ `phase2_background`（MCP connect + agent build，容错不致命）。
- 修改 `backend/app/main.py`：lifespan 先跑 Phase1，再 `asyncio.create_task(phase2_background)` 后台执行；退出时取消 task。
- 修改 `backend/app/api/routes/monitor.py`：`/health` 读取 `app.state.agent_ready`。
- 新增 `backend/tests/test_phase1_core.py`。

**核心变更**：
```python
# agent_factory.py 关键片段
middleware = [ObservabilityMiddleware()] + (extra_middleware or [])
agent = create_deep_agent(model=..., tools=all_tools, subagents=...,
    middleware=middleware, interrupt_on=DEFAULT_INTERRUPT, ...)
```
```python
# ToolCallRequest 实测结构：tool_call(dict) / tool / state / runtime
name = request.tool_call.get("name")   # 用于事件与后续 Guard
```

**问题与解决**：
- 问题：`wrap_tool_call` 的 `request` 结构未知。
- 解决：实测 `ToolCallRequest` 为 dataclass，字段 `tool_call/tool/state/runtime`，据此编写中间件，`tool_call` 含 `name/args/id`。
- 问题：`/health` 无法拿到就绪标志。
- 解决：两阶段启动把 `agent_ready` 写入 `app.state`，health 端点读取 `request.app.state`。

**验证**：`pytest -q` → 6 passed（含 Phase0）。

### [Phase 0] 项目校准 — 已完成

**实现思路**：为后续所有阶段建立可验证基础：扩展配置与事件类型、锁定测试依赖、搭建 pytest 骨架，确保「代码可导入 + 单测可跑」的基线始终成立。

**修改文件**：
- `backend/app/core/config.py`：新增 `api_token`、ToolGuard（`tool_guard_enabled/level/denied_tools/file_guard_deny_dirs`）、多智能体（`default_agent_id/agents_root/agent_idle_ttl_minutes`）、心跳（`heartbeat_*`）、`ollama_base_url`、`lang` 字段；新增 `denied_tools_list`/`file_deny_dirs_list` 属性。
- `backend/app/core/observability.py`：`EventType` 新增 10 个枚举（PLAN_CREATED/CONFIRMED、GUARD_BLOCK/APPROVED、APPROVAL_REQUESTED、SKILL_LOADED、CRON_TRIGGER、HEARTBEAT、MCP_RECOVER、PROVIDER_RETRY）。
- `backend/requirements.txt`：新增 `pytest`、`pytest-asyncio`。
- `backend/.env.example`：追加安全/多智能体/心跳/Provider/i18n 配置样例。
- `backend/pytest.ini`：`asyncio_mode=auto`，`testpaths=tests`。
- `backend/tests/__init__.py`、`backend/tests/test_smoke.py`：冒烟测试（app 导入、config 新字段、事件类型）。

**核心变更**：配置层新增分组字段与派生属性；事件枚举对齐可观测性规范 C.5。

**问题与解决**：
- 问题：`pytest` 未安装（venv 里 requirements 曾装但 pytest 是本阶段新增）→ `No module named pytest`。
- 解决：`pip install pytest pytest-asyncio` 后 `pytest -q` 通过（3 passed）。

**验证**：`.venv\Scripts\python -m pytest -q` → 3 passed。
