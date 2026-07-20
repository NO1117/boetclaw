# BoetClaw 功能清单

> 文档基线：2026-07-17。  
> 编号规则：`FUN-xxx`。需求映射见 [REQUIREMENTS.md](./REQUIREMENTS.md)。状态以当前代码闭环为准。
> 最近验证基线（2026-07-20）：后端 pytest `213 passed`；Vitest `5 files / 29 passed`；Playwright E2E `8 passed`（fake Provider）；ruff/mypy/OpenAPI/coverage/build/compose 均通过；CI workflow 已落盘。PLAN-600—710 运维闭环已完成；跨进程、多副本及重启后取消仍不支持。

## 1. Agent 与交互

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-001 | 同步智能对话 | REQ-100 | Agent/API | `backend/app/api/routes/agent.py`；`backend/app/core/agent.py` | 已实现 | HTTP 异常统一映射仍较粗，运行错误多返回 500 |
| FUN-002 | SSE 流式对话 | REQ-101、REQ-108 | Agent/API/前端 | `services/chat_orchestration.py`；`services/run_registry.py`；`agents/runtime.py`；`agent.py`；`frontend/src/services/sse.ts`；`frontend/src/services/chatStream.ts`；`ChatPanel.tsx` | 已实现 | v1 envelope、Workspace 流式、中断/命令/语言/source/session 和单进程取消已统一；PLAN-400 协议/组件测试已完成 |
| FUN-003 | Plan 规划门控 | REQ-102 | Agent 中间件 | `middleware/plan_gate_mw.py`；`agents/state.py`；`core/checkpoint.py` | 已实现 | 默认 SQLite 支持单机重启恢复；memory 降级不支持 |
| FUN-004 | 计划批准/拒绝/编辑 | REQ-103 | Agent/API/前端 | `services/plan_resume.py`；`services/execution_resume.py`；`agents/resolver.py`；`api/routes/agent.py`；`PlanConfirm.tsx` | 已实现 | 多 Agent approve/edit/reject、重建恢复、删除/错误 ref 和 default 兼容已测；仅单实例 |
| FUN-005 | 计划历史与失败审计 | REQ-103 | 记忆/API | `memory/plan_history_store.py` | 已实现 | 支持 Agent+thread 筛选和旧 JSON；JSON 文件无并发事务 |
| FUN-006 | 会话历史、搜索、恢复、导出、删除、归档 | REQ-104 | 记忆/API/前端 | `memory/session_store.py`；`api/routes/agent.py`；`App.tsx` | 已实现 | 无分页游标和并发控制；删除/归档不清理 Trace 或 checkpoint |
| FUN-007 | Slash 命令 | REQ-105、REQ-106 | Commands/i18n | `commands/registry.py`；`i18n/__init__.py` | 已实现 | 国际化仅 zh/en，主要覆盖命令文案 |
| FUN-008 | 默认子智能体 | REQ-121 | Agent | `core/agent_factory.py` | 已实现 | 子智能体配置不可通过管理 API 动态编辑 |
| FUN-009 | 上下文摘要 | REQ-303 | Agent 中间件 | `core/agent_factory.py` | 部分实现 | 默认关闭；依赖运行时兼容，失败会降级禁用 |
| FUN-010 | 长期记忆后端选择 | REQ-303 | Memory | `memory/store_backend.py` | 部分实现 | `store` 实际为 `InMemoryStore`，不跨重启 |

## 2. 工具与扩展

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-020 | 内置文本/图表/代码/钻井工具 | REQ-120、REQ-204 | Tools | `tools/builtin.py` | 已实现 | 外部依赖、绘图环境和输入质量影响结果 |
| FUN-021 | 工具统一组装 | REQ-122 | Agent Factory | `core/agent_factory.py` | 已实现 | `/tools` 统计口径对插件工具展示有限 |
| FUN-022 | MCP 服务器连接与工具发现 | REQ-123 | Tools/MCP | `tools/mcp_manager.py` | 已实现 | 配置来自环境 JSON；运行可用性受外部进程/网络影响 |
| FUN-023 | MCP 状态、详情和重载 | REQ-123 | API/前端 | `api/routes/tools.py`；`McpManager.tsx` | 已实现 | 无在线配置编辑与细粒度单服务器操作 |
| FUN-024 | 插件发现和安全默认加载 | REQ-124 | Plugins | `plugins/loader.py`；`plugins/registry.py` | 已实现 | 进程内动态加载仍具有代码执行风险 |
| FUN-025 | 插件安装、详情、启停、重载、扫描与删除 | REQ-124、REQ-125 | API/前端 | `api/routes/plugins.py`；`PluginsManager.tsx` | 已实现 | 安装源为服务器目录；扫描为静态正则；启用后仍无 OS/容器沙箱 |
| FUN-026 | Provider 抽象 | REQ-004 | Providers | `providers/base.py`；`providers/manager.py` | 已实现 | 仅 OpenAI/Anthropic/Ollama |
| FUN-027 | Provider 配置、模型、检测与默认切换 | REQ-004 | API/前端 | `api/routes/providers.py`；`ProviderSettings.tsx` | 已实现 | API Key 写入明文 `.env`；运行中的已构建 Agent 不一定自动重建 |
| FUN-028 | Provider 模型解析限流 | REQ-306 | Providers | `providers/rate_limiter.py`；`providers/manager.py` | 部分实现 | 限制模型解析/构建，不等同于每次 LLM 调用限流 |

## 3. 技能与多 Agent

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-040 | 全局技能池 | REQ-140 | Skills | `skills_system/pool_service.py`；`skills_system/store.py` | 已实现 | 文件系统元数据，无版本仓库 |
| FUN-041 | 工作区技能副本与启停 | REQ-140 | Skills | `skills_system/workspace_service.py` | 已实现 | 状态为工作区 JSON 文件 |
| FUN-042 | 技能详情、文件编辑、删除 | REQ-140 | API/前端 | `api/routes/skills.py`；`SkillsManager.tsx` | 已实现 | 仅允许受支持文本扩展名 |
| FUN-043 | 技能安全扫描 | REQ-141 | Skills/Security | `skills_system/scanner.py` | 已实现 | 基于特征规则，不是沙箱或完整恶意代码分析 |
| FUN-044 | 技能 Reload | REQ-142 | Skills/Agents | `api/routes/skills.py`；`multi_agent_manager.py` | 已实现 | 仅重建已加载 Agent；进行中运行的协调策略未定义 |
| FUN-045 | Agent 创建、列表、详情和切换 | REQ-143 | Agents/API/前端 | `agents/multi_agent_manager.py`；`api/routes/agents.py` | 已实现 | 列表扫描磁盘（跳过 tombstone）；元数据懒加载，不强制 build graph |
| FUN-046 | Agent 文件系统隔离 | REQ-143、REQ-301 | Agents/DeepAgents | `agents/workspace.py`；`multi_agent_manager.py` | 已实现 | 属于应用路径隔离，不是 OS/容器安全隔离 |
| FUN-047 | Agent 删除 | REQ-143 | Agents/API/前端 | `multi_agent_manager.py`；`api/routes/agents.py`；`CheckpointProvider.purge` | 已实现 | 默认 tombstone；`purge=true` 清目录+checkpoint；default 拒绝；resume 409 |
| FUN-048 | Agent 文件与运行历史聚合 | REQ-144 | Agents/API/前端 | `api/routes/agents.py`；`App.tsx` | 已实现 | 任务标题回退匹配为启发式；无统一运行实体 |
| FUN-049 | Agent 空闲逐出 | REQ-304、REQ-145 | Agents | `multi_agent_manager.py`；`services/agent_idle.py` | 已实现 | 单进程内存逐出；不清理 checkpoint、会话 JSON、计划历史或磁盘文件 |

## 4. 安全与身份

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-060 | ToolGuard 四级策略 | REQ-160 | Security | `security/engine.py`；`security/execution_level.py` | 已实现 | 规则引擎不能替代系统级权限隔离 |
| FUN-061 | 规则/文件/Shell Guardian | REQ-160、REQ-302 | Security | `security/guardians/` | 已实现 | 基于规则和参数检查，存在绕过风险 |
| FUN-062 | 工具人工审批 | REQ-161 | Middleware/Security/API | `tool_guard_mw.py`；`security/approval.py`；`services/approval_resume.py` | 已实现（单实例） | 稳定 key、真实 interrupt/resume、并发互斥和拒绝零执行已测；跨资源崩溃窗口不保证 exactly-once |
| FUN-063 | 审批历史持久化和重启恢复 | REQ-162 | Security/Checkpoint | `security/approval.py`；`core/checkpoint.py`；`services/execution_resume.py` | 已实现 | SQLite 保留 pending 并校验 checkpoint；处理中重启和恢复失败进入不可自动重试终态；memory 重启显式过期 |
| FUN-064 | API Token/JWT 鉴权 | REQ-163、REQ-164 | Middleware/Auth | `api_security_mw.py`；`security/console_auth.py` | 已实现 | `/auth/*` 全部豁免中间件；适用于本地单用户而非 RBAC |
| FUN-065 | API token/IP 限流 | REQ-163 | Middleware | `api_security_mw.py` | 已实现 | 单进程内存计数，多实例不共享 |
| FUN-066 | Console 登录/退出 | REQ-164 | Auth/前端 | `api/routes/auth.py`；`App.tsx` | 已实现 | Token 同时进入 localStorage，需防范 XSS；无账户锁定 |
| FUN-067 | 渠道白名单 | REQ-165 | Gateway/Security | `gateway/access_control.py` | 已实现 | 空白名单默认开放 |
| FUN-068 | 渠道用户级限流 | REQ-165 | Gateway | `gateway/manager.py` | 已实现 | 单进程内存窗口 |
| FUN-069 | 多用户 RBAC | REQ-167、REQ-020 | Identity | — | 待实现 | 无用户、角色、租户、资源授权模型 |

## 5. 任务、调度与渠道

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-080 | 后台任务创建、列表、详情和状态筛选 | REQ-180、REQ-181 | Tasks/API/前端 | `services/task_scheduler.py`；`services/run_registry.py`；`api/routes/tasks.py` | 已实现 | 单进程受控 task，不是持久化可靠任务队列 |
| FUN-081 | 任务重跑 | REQ-180 | Tasks | `api/routes/tasks.py` | 已实现 | 活动任务拒绝重复运行；跨进程无分布式锁 |
| FUN-082 | 任务取消 | REQ-180 | Tasks | `services/run_registry.py`；`api/routes/tasks.py` | 已实现（单进程） | 取消底层协程并等待确认，终态安全；不支持跨进程/重启后取消 |
| FUN-083 | 任务历史持久化/重启恢复 | REQ-181 | Tasks | `services/task_scheduler.py` | 已实现 | JSON 全量重写，无锁和原子替换 |
| FUN-084 | Cron CRUD、启停和手动触发 | REQ-182 | Scheduling | `services/cron_service.py`；`api/routes/cron.py` | 已实现 | 时区固定 UTC |
| FUN-085 | Cron 运行历史 | REQ-182 | Scheduling | `services/cron_service.py` | 已实现 | `cron_history.json` 落盘，上限 500；与 job 配置分文件 |
| FUN-086 | Heartbeat | REQ-183 | Scheduling | `services/heartbeat.py`；`api/routes/cron.py` | 已实现 | PUT 写 `.env` `HEARTBEAT_*` 并热重调度；响应含 `persisted` |
| FUN-087 | 四渠道接入与 webhook 验签 | REQ-166、REQ-184 | Gateway | `services/gateway/channels/`；`api/routes/gateway.py` | 已实现（可配置） | 路由验签已接入；未配密钥 `skipped`；真实回发/联调取决于凭据 |
| FUN-088 | 渠道队列和回发 | REQ-184 | Gateway | `services/gateway/manager.py`；`api/routes/gateway.py` | 部分实现 | 入队失败会回退 BackgroundTasks，弱化统一背压语义 |
| FUN-089 | 渠道状态、消息审计和失败重试 | REQ-185 | Gateway/API/前端 | `gateway/manager.py`；`ChannelsManager.tsx` | 已实现 | 重启恢复记录不能重试，因为原消息对象未持久化 |

## 6. 钻井领域与产物

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-100 | 井 CRUD | REQ-200 | Domain/API/前端 | `domain/store.py`；`api/routes/domain.py`；`App.tsx` | 已实现 | 有关联数据时 409，不提供级联删除 |
| FUN-101 | 井段管理 | REQ-201 | Domain/API/前端 | 同上 | 已实现 | API/UI 完整 CRUD |
| FUN-102 | 日报管理 | REQ-202 | Domain/API/前端 | 同上 | 已实现 | API/UI 完整 CRUD、井筛选和删除确认 |
| FUN-103 | 钻井参数管理 | REQ-202 | Domain/API/前端 | 同上；`tools/builtin.py` | 已实现 | 单条 CRUD 完整；批量导入未排期 |
| FUN-104 | LAS 登记 | REQ-203 | Domain/API/前端 | `api/routes/domain.py`；`App.tsx` | 已实现 | 记录 CRUD 完整；直接登记仍可不解析 |
| FUN-105 | LAS 路径导入与上传解析 | REQ-203 | Domain/API/前端 | `domain/las_importer.py`；`api/routes/domain.py`；`App.tsx` | 已实现 | 上传有大小、扩展名和轻量内容门禁；服务器路径导入仍依赖部署侧路径权限 |
| FUN-106 | 领域 JSON 存储 | REQ-206、REQ-309 | Domain | `domain/store.py` | 已实现（单实例） | 锁、关系校验、schema version、备份和原子 replace；无跨进程事务/数据库迁移 |
| FUN-107 | 图表/代码产物生成 | REQ-204 | Tools | `tools/builtin.py` | 已实现 | 产物类型固定为图表与代码 |
| FUN-108 | 产物侧车元数据 | REQ-204 | Run Context | `core/run_context.py` | 已实现 | 依赖生成时上下文；旧文件可能没有元数据 |
| FUN-109 | 产物列表、筛选、预览、下载、删除和校验和 | REQ-205 | Files/API/前端 | `api/routes/files.py`；`App.tsx` | 已实现 | 无保留策略与访问控制细分；删除不清理 Trace/任务记录 |

## 7. 可观测性、前端与部署

| 功能编号 | 功能 | 关联需求 | 模块 | 主要实现路径 | 状态 | 主要缺口 |
|---|---|---|---|---|---|---|
| FUN-120 | Trace 事件采集 | REQ-220 | Observability/Middleware | `core/observability.py`；`observability_mw.py` | 已实现 | 本地内存和 JSONL，非集中式追踪后端 |
| FUN-121 | Trace/Run 查询与时间线 | REQ-221 | API/前端 | `api/routes/agent.py`；`monitor.py`；`core/timeline.py` | 已实现 | 数据规模大时缺索引和分页 |
| FUN-122 | 健康和统计 | REQ-220、REQ-300 | Monitor | `api/routes/monitor.py` | 已实现 | 健康表示进程/Agent 就绪，不涵盖所有外部依赖 |
| FUN-123 | Prometheus 指标 | REQ-222 | Monitor | `api/routes/monitor.py` | 已实现 | 手工文本聚合，非标准客户端注册表 |
| FUN-124 | OpenTelemetry/LangSmith | REQ-223 | Observability | `core/otel.py`；`core/config.py` | 已实现 | 无默认 OTLP exporter 配置；控制台 exporter 默认关闭 |
| FUN-125 | React 管理控制台 | REQ-010—REQ-014 | Frontend | `frontend/src/App.tsx`；`frontend/src/components/`；Vitest/Playwright | 已实现 | 关键组件/协议与 fake E2E 已覆盖；非关键页深度组件覆盖仍薄；真实 Provider/渠道为 manual |
| FUN-126 | 轻量客户端路由 | REQ-401 | Frontend | `App.tsx` | 已实现 | 手写 History API 路由，无路由库级嵌套/守卫 |
| FUN-127 | 两阶段启动与优雅关闭 | REQ-300 | Core | `core/startup.py`；`main.py` | 已实现 | Phase 2 失败仅记录日志，需依赖 health 判断 |
| FUN-128 | Docker 单体镜像/后端托管 UI | REQ-307 | Deployment | `Dockerfile`；`main.py` | 已实现 | `/ui` 仅在镜像中存在构建产物时挂载 |
| FUN-129 | Compose 前后端分离部署 | REQ-307 | Deployment | `docker-compose.yml`；`deploy/nginx.conf` | 已实现 | 默认本地卷和单副本，不是 HA |
| FUN-130 | OpenAPI 文档 | REQ-308 | API | FastAPI `/docs`、`/openapi.json` | 已实现 | 本文件仅索引；运行时 OpenAPI 才是字段契约真源 |
| FUN-131 | 数据库与多实例架构 | REQ-021、REQ-305、REQ-309 | Platform | — | 待实现 | checkpoint 仅为单机 SQLite；本地 JSON、内存限流、APScheduler 与多实例 checkpoint 均需替换/协调 |
