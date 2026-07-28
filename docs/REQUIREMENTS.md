# BoetClaw 项目需求说明

> 版本基线：2026-07-17。本文以当前代码为事实来源，归档实施计划与进度仅用于解释设计意图。  
> 状态定义：**已实现**＝代码中存在可用闭环；**部分实现**＝主路径存在但有明确能力或可靠性缺口；**待实现**＝当前代码没有对应闭环。
> 最近验证基线（2026-07-20）：后端 pytest `213 passed`；前端 Vitest `5 files / 29 passed`、Playwright E2E `8 passed`（fake Provider）；ruff/mypy/OpenAPI/coverage/build/compose 均通过；CI workflow 已落盘、云端 Actions 待启用。PLAN-210 单进程取消已闭环；跨进程、多副本及重启后取消不在已实现范围。

## 1. 项目定位与业务目标

BoetClaw 是面向钻井业务的本地优先智能体工作台。系统以 DeepAgents/LangGraph 为执行内核，通过 Web 控制台、REST/SSE 和外部消息渠道提供规划、工具调用、人工审批、领域数据管理、任务调度与运行追踪能力。

| 编号 | 需求 | 状态 | 验收摘要 |
|---|---|---|---|
| REQ-001 | 提供从自然语言请求到规划、执行、产出和追踪的智能体闭环 | 部分实现 | 同步/SSE、单机持久 checkpoint、工具审批、多 Agent 计划确认、单进程取消、fake-Provider E2E 与 CI workflow 已闭环；真实 Provider/渠道仍非默认门禁，云端 Actions 待启用 |
| REQ-002 | 支持钻井井、井段、日报、参数和 LAS 数据沉淀，并供 Agent 查询和生成产物 | 已实现 | 领域 API、LAS 上传/解析/质检、真实参数查询和产物中心均有代码路径 |
| REQ-003 | 将高风险工具执行置于规则检查和人工审批边界内 | 已实现（单实例） | ToolGuard、稳定审批 key、完整 ExecutionRef、fail-closed、并发互斥和真实 LangGraph 恢复已验证；跨资源崩溃窗口不保证 exactly-once |
| REQ-004 | 支持多 Agent 工作区、技能、插件、MCP 和多模型扩展 | 部分实现 | 扩展机制、每 Agent checkpoint 隔离、计划确认、流式路由、插件扫描/删除与 Agent 磁盘发现/purge 已闭环；真实 Provider/渠道仍非默认门禁 |
| REQ-005 | 支持 Web、定时任务、心跳及多消息渠道触达 | 部分实现 | 四类 webhook、队列、Cron history 落盘、Heartbeat `.env` 持久与路由验签已闭环；真实回发仍取决于平台凭据与联调 |
| REQ-006 | 提供可部署、可监控、可审计的单实例运行形态 | 部分实现 | Docker、健康检查、Trace、Prometheus、可选 OTel 已实现；高可用、数据库和多实例协调待实现 |

## 2. 用户角色

| 编号 | 角色 | 核心诉求 | 状态 |
|---|---|---|---|
| REQ-010 | 钻井工程师/分析人员 | 对话查询、生成日报/图表/代码，维护井与参数数据 | 已实现 |
| REQ-011 | Agent 使用者 | 使用计划确认、会话恢复、任务管理和产物追踪 | 部分实现 |
| REQ-012 | 平台管理员 | 配置 Provider、安全策略、技能、插件、MCP、渠道和调度 | 已实现 |
| REQ-013 | 安全审批人 | 查看风险发现、批准/拒绝工具调用并查阅历史 | 已实现（单实例审批闭环；跨资源崩溃窗口不保证 exactly-once） |
| REQ-014 | 外部渠道用户 | 从钉钉、飞书、QQ、Telegram 发起请求并接收回复 | 部分实现 |
| REQ-015 | 多租户管理员 | 管理用户、组织、角色、细粒度权限和数据租户 | 待实现 |

## 3. 范围

### 3.1 当前范围

- 单实例 FastAPI 服务和 React 控制台。
- OpenAI、Anthropic、Ollama Provider。
- 同步对话、SSE 流式输出、计划确认、工具审批、子智能体。
- 全局技能池、Agent 工作区技能、插件与 MCP 工具。
- 任务、Cron、Heartbeat、四类消息渠道。
- 井、井段、日报、钻井参数、LAS 和图表/代码产物。
- 文件型持久化、Trace/指标、API Token 和可选 Console 密码登录。

### 3.2 明确不在当前已实现范围

| 编号 | 需求 | 状态 |
|---|---|---|
| REQ-020 | 多用户账号、RBAC、租户隔离、SSO/OIDC | 部分实现 | 单工作区用户/角色/资源 ACL 已落地；租户隔离与 SSO/OIDC 不做 |
| REQ-021 | 领域/审计 PostgreSQL/SQLite 事务存储、分布式队列和多实例调度 | 待实现（仅 LangGraph checkpoint 已使用单机 SQLite） |
| REQ-022 | 生产级密钥库、密钥轮换和字段级加密 | 待实现 |
| REQ-023 | WITSML、实时井场流数据和完整行业数据治理 | 待实现 |
| REQ-024 | 移动端原生客户端及除现有四类外的渠道适配 | 待实现 |

## 4. 功能需求

### 4.1 Agent、会话与计划

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-100 | 接收消息并返回 thread_id、trace_id、run_id、响应、todos 和中断状态 | 已实现 | 中断响应额外返回服务端生成的 `execution_ref` 与 payload |
| REQ-101 | 支持版本化 SSE 输出 update/done/error/interrupt/command 事件 | 已实现 | v1 envelope、完整 block 解析、done once、服务/网络错误可见；前端停止会先 abort 再请求服务端取消 |
| REQ-102 | `/plan` 进入规划态，非规划工具受门控，计划生成后等待确认 | 已实现 | `PlanGateMiddleware` + LangGraph interrupt |
| REQ-103 | 支持 approve、reject、edit 恢复，并记录成功和失败历史 | 已实现 | 完整 ref、pending/checkpoint 校验、按 Agent/thread 历史及多 Workspace API/SQLite 重建恢复已验证 |
| REQ-104 | 提供会话列表、搜索、恢复、Markdown 导出、删除和归档 | 已实现 | `workspace/sessions/*.json`；默认列表隐藏已归档 |
| REQ-105 | 支持 `/new`、`/clear`、`/stop`、`/plan`、`/restart`、`/help` 等命令 | 已实现 | 命令预解析；`/stop` 按 Agent+thread 取消当前活动 run，无运行明确响应 |
| REQ-106 | 普通对话支持请求体语言与 `Accept-Language` 国际化 | 部分实现 | 同步/流式请求语言上下文已统一，slash command 与 ToolGuard 提示接入；模型输出语言仍取决于提示与 Provider |
| REQ-107 | 中断状态跨服务重启后可继续恢复 | 已实现（单实例） | 默认 SQLite、每 Agent 独立 DB；按 ExecutionRef 重建 graph 并校验 interrupt；memory 明确不支持 |
| REQ-108 | 非默认 Agent 的同步与流式调用行为一致 | 已实现 | 两入口共用请求预处理和严格 resolver，Workspace graph 通过自身 `astream` 执行；恢复仍使用同一 Agent 标识 |

### 4.2 工具、子智能体与扩展

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-120 | 提供文本审查/生成、图表、代码和钻井参数查询等内置工具 | 已实现 | `backend/app/tools/builtin.py` |
| REQ-121 | 提供 researcher、coder、chart-analyst、reviewer 子智能体 | 已实现 | 由 Agent Factory 默认构建 |
| REQ-122 | 合并内置、MCP 与已启用插件工具 | 已实现 | Agent Factory 统一组装 |
| REQ-123 | 查看 MCP 服务器、工具详情并重载连接/工具 | 已实现 | tools 管理 API 和控制台 |
| REQ-124 | 安装、查看、启停和重载插件，默认不加载未启用插件 | 已实现 | `ENABLED_PLUGINS` 持久化到 `.env`；DELETE 同步清目录与启用列表 |
| REQ-125 | 插件安装前执行与技能同等级别的静态安全扫描 | 已实现 | 复用 `SkillScanner`；不安全拒绝安装；提供 scan-report / scan API |

### 4.3 技能与多 Agent

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-140 | 管理全局技能池与每 Agent 工作区技能副本 | 已实现 | 列表、安装、复制、启停、详情、文本文件编辑、删除 |
| REQ-141 | 技能安装或查看时扫描密钥和危险脚本特征 | 已实现 | `SkillScanner` |
| REQ-142 | 技能变更后重建指定或已加载 Agent | 已实现 | `POST /skills/reload` |
| REQ-143 | 创建、查看、切换和删除 Agent，隔离其 files 与技能目录 | 已实现 | 运行时隔离；默认 tombstone 注销，可选 `purge` 清盘与 checkpoint；default 不可删 |
| REQ-144 | 按 Agent 聚合文件索引、任务和会话历史 | 已实现 | agents files/history API |
| REQ-145 | Agent 配置在重启后自动发现并恢复 | 已实现 | `list_agents`/详情可扫描非 tombstone 磁盘目录；定向 resolver 可懒加载重建 graph |

### 4.4 安全与访问控制

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-160 | ToolGuard 支持 strict/smart/auto/off 级别及规则、文件、Shell Guardian | 已实现 | 默认 smart，敏感路径和高风险命令受检查 |
| REQ-161 | 风险工具可中断等待人工批准或拒绝 | 已实现（单实例） | 真实 LangGraph 测试验证 approve 单次执行、reject 零执行、节点重放复用审批、重复/并发裁决互斥及非默认 Agent resolver |
| REQ-162 | 审批历史跨重启保持 pending 并可审计；不可恢复时明确失败 | 已实现 | SQLite 可恢复 pending；恢复失败或重启遇到 resuming 转不可自动重试的 `resume_failed`，旧缺 ref/checkpoint 缺失返回 409 |
| REQ-163 | API 支持 Bearer/X-API-Token 与按 token 优先、IP 兜底限流 | 已实现 | 默认无 Token、限流为 0 时开放 |
| REQ-164 | Console 可选密码登录并签发短期 JWT | 已实现 | 用户名+密码 + 兼容仅密码；HttpOnly Cookie + CSRF；HMAC-SHA256 JWT |
| REQ-165 | 渠道按 platform/user_id 白名单与用户级限流 | 已实现 | 空白名单兼容放行 |
| REQ-166 | Webhook 必须进行生产级平台签名验证 | 已实现（可配置） | 路由早期调用 `verify_signature`；配置密钥强制校验，未配置 `signature=skipped`；不含飞书 encrypt 解密与真实平台联调 |
| REQ-167 | 用户、角色、资源级授权和审计主体关联 | 已实现 | 单实例单工作区；Argon2id、会话撤销、资源 ACL、审计 cursor；无租户/SSO |

### 4.5 任务、调度与渠道

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-180 | 创建、查询、筛选、运行和取消后台任务 | 已实现（单进程） | 受控 `asyncio.Task`、取消确认、幂等重复取消和安全终态已实现；不支持跨进程/重启后取消 |
| REQ-181 | 服务重启恢复任务历史，并把遗留 running 标为 failed | 已实现 | `task_history.json` |
| REQ-182 | Cron 支持创建、编辑、启停、删除、手动触发和历史查询 | 已实现 | Job 与运行历史分文件落盘（`cron_jobs.json` / `cron_history.json`，历史上限 500） |
| REQ-183 | Heartbeat 支持启停、间隔和提示词配置 | 已实现 | PUT 写入 `.env` 的 `HEARTBEAT_*` 并热重调度；重启后配置不回退 |
| REQ-184 | 钉钉、飞书、QQ、Telegram webhook 经队列执行并回发 | 部分实现 | 主链路与路由验签已存在；真实回发依赖凭据与平台网络，未知平台返回 503 |
| REQ-185 | 渠道状态、队列深度、消息历史、失败重试可运维 | 已实现 | 历史最近 500 条落盘；重启恢复记录没有原消息对象，不能重试 |

### 4.6 钻井领域与产物

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-200 | 井对象支持列表、新建、详情、更新和删除 | 已实现 | 完整 REST CRUD；有领域/产物依赖时删除返回 409 |
| REQ-201 | 井段支持按井列表、新建、详情、更新和删除 | 已实现 | API 与井详情页均支持完整生命周期 |
| REQ-202 | 日报和钻井参数支持按井筛选、完整 CRUD | 已实现 | API 完整 CRUD；页面支持详情/编辑/删除确认和筛选保留 |
| REQ-203 | LAS 支持登记、服务器路径导入、本地上传、解析、质量摘要和记录 CRUD | 已实现 | 上传有扩展名/大小/轻量内容门禁；删除只清理托管曲线/上传文件，外部源文件保留 |
| REQ-204 | 生成图表和代码并自动写入 task/trace/run/agent/well 元数据 | 已实现 | 侧车元数据由运行上下文写入 |
| REQ-205 | 产物支持类型、井号、Agent 筛选、预览与下载 | 已实现 | 图表 PNG、代码文本 |
| REQ-206 | 领域数据关系约束、安全删除、版本和并发控制 | 已实现（单实例） | `well_id` 在锁内校验；井依赖删除 409；schema_version/进程内锁已实现，不提供多实例事务 |

### 4.7 可观测性与运维

| 编号 | 需求 | 状态 | 事实与边界 |
|---|---|---|---|
| REQ-220 | 记录 Agent、工具、计划、安全、渠道、Cron 和 MCP 事件 | 已实现 | TraceStore 内存 + JSONL |
| REQ-221 | 按 Trace/Run 查询事件并生成含间隔、分类、耗时的时间线 | 已实现 | raw trace 与 timeline API |
| REQ-222 | 暴露健康、统计和 Prometheus 文本指标 | 已实现 | 健康检查免鉴权限流 |
| REQ-223 | 可选启用 FastAPI OpenTelemetry 和 LangSmith | 已实现 | OTel 控制台导出默认关闭 |
| REQ-224 | 日志、Trace 和指标接入集中式生产后端并配置告警 | 待实现 | 当前主要为本地 JSONL/文本端点 |

## 5. 非功能需求

| 编号 | 需求 | 状态 | 验收原则 |
|---|---|---|---|
| REQ-300 | 快速启动：轻量初始化先完成，模型/MCP 后台初始化 | 已实现 | `/api/v1/monitor/health` 区分 ready 与 agent_ready |
| REQ-301 | 工作区文件、技能与 Agent 文件后端路径隔离 | 已实现 | 不同 Agent 的 `files/` 根目录不同 |
| REQ-302 | 路径输入必须限制在允许根目录内 | 部分实现 | 文件、技能、插件上传有安全拼接；服务器路径导入和部分管理输入仍需部署侧约束 |
| REQ-303 | 数据在单实例重启后尽可能恢复 | 部分实现 | checkpoint、任务、会话、审批、计划、领域、Trace、Cron history、Heartbeat 配置等落盘；`InMemoryStore` 长期记忆仍不跨重启 |
| REQ-304 | 支持单实例异步并发和渠道队列背压 | 已实现 | FastAPI async、每渠道有界队列 |
| REQ-305 | 支持多实例横向扩展且行为一致 | 待实现 | 内存状态、APScheduler 与本地 JSON 不支持无协调多副本 |
| REQ-306 | 默认本地开发低门槛，生产可开启鉴权和限流 | 已实现 | Token、Console 密码、API/渠道/Provider 限流均可配置 |
| REQ-307 | 前后端可独立部署，也可由后端托管已构建前端 | 已实现 | Nginx 拓扑与 `/ui` 静态挂载均存在 |
| REQ-308 | 所有公开 REST 契约有运行时 OpenAPI 描述 | 已实现 | `/docs`、`/openapi.json` |
| REQ-309 | 数据写入具备原子性、并发控制、备份与迁移 | 部分实现 | DomainStore 已有锁、备份、原子 replace、版本及旧 JSON 兼容；其他 JSON/JSONL 和数据库迁移不在 PLAN-300 |
| REQ-310 | 全量 UI、业务文案和 Agent 输出支持多语言 | 部分实现 | 当前仅中文为主，命令和安全提示提供 zh/en |

## 6. 技术与业务约束

| 编号 | 约束 | 状态 |
|---|---|---|
| REQ-400 | 后端采用 Python/FastAPI，Agent 采用 DeepAgents/LangGraph | 已实现 |
| REQ-401 | 前端采用 React/TypeScript，使用 History API 轻量路由 | 已实现 |
| REQ-402 | API 业务前缀统一为 `/api/v1` | 已实现 |
| REQ-403 | 当前持久化根目录默认为 `backend/workspace`，技能池为 `backend/skills` | 已实现 |
| REQ-404 | 默认部署是单机、单用户友好；外部模型/渠道能力受凭据和网络约束 | 已实现 |
| REQ-405 | 高风险工具判断是辅助控制，不替代 OS 容器、最小权限和网络隔离 | 部分实现 |

## 7. 验收原则

1. **代码优先**：状态以路由、服务、前端调用和测试代码为准，不因历史计划标记“完成”而自动判定已实现。
2. **契约优先**：REST 字段、状态码和可选参数以运行实例的 `/docs` 与 `/openapi.json` 为最终契约。
3. **闭环验收**：只有“入口—服务—持久化/副作用—查询或 UI”全部接通才标记已实现。
4. **降级透明**：无模型 Key、MCP、渠道凭据时允许服务启动，但相关功能必须暴露未配置/失败状态，不能宣称真实外部调用成功。
5. **安全验收**：覆盖未授权 401、限流 429、敏感路径拒绝、审批批准/拒绝、重启后 pending 保留与不可恢复 409，以及渠道白名单。
6. **数据验收**：验证 checkpoint、任务、会话、计划、审批、Trace、领域数据、Cron history、Heartbeat 配置跨重启恢复；明确 `memory` checkpoint 降级与 `InMemoryStore` 等非持久边界。
7. **隔离验收**：至少两个 Agent 对同名文件互不可见；同时验证默认 Agent 与非默认 Agent 的同步调用。
8. **部署验收**：后端健康检查、`/docs`、前端路由回退、Nginx `/api/` 代理和可选 Ollama profile 可用。
9. **回归验收**：后端 pytest 与前端 build 通过；涉及真实 Provider/渠道的用例可用 mock 验证，并另行做有凭据冒烟。
