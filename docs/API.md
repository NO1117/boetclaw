# BoetClaw REST API 索引

> 代码基线：`backend/app/main.py` 与 `backend/app/api/routes/*.py`（2026-07-17）。  
> **所有业务接口统一前缀为 `/api/v1`。运行实例的 `/docs` 和 `/openapi.json` 是请求字段、响应模型、校验规则及状态码的契约真源；本文是便于检索的人工索引。**
> 最近验证基线（2026-07-20）：后端 pytest `213 passed`；Vitest `5 files / 29 passed`；E2E `8 passed`（fake Provider）；ruff/mypy/OpenAPI/coverage/build/compose 均通过。PLAN-600—710 运维闭环（Cron history、Heartbeat 持久、渠道路由验签、插件扫描删除、Agent 磁盘发现/purge、idle 逐出、会话删除/归档、产物删除、产物校验和、LAS 上传门禁及文档同步）已完成。跨进程锁、数据库迁移、真实 Provider/渠道联调不在已完成范围。

## 1. 通用约定

### 1.1 非业务入口

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/` | 返回服务名、版本、`/docs`、API 前缀和 `/ui/` 提示 |
| `GET` | `/docs` | FastAPI Swagger UI |
| `GET` | `/openapi.json` | OpenAPI JSON |
| 静态 | `/ui/*` | 仅当后端存在 `frontend_dist` 时挂载 React 构建产物 |

### 1.2 鉴权与限流

- 当 `API_TOKEN` 和 `CONSOLE_PASSWORD` 都为空时，API 默认开放。
- 配置后可使用 `Authorization: Bearer <API_TOKEN|Console JWT>`、`X-API-Token: <API_TOKEN>` 或 Console JWT cookie。
- `/api/v1/auth/*`、`/api/v1/monitor/health` 与 `/api/v1/gateway/*/webhook` 豁免中间件鉴权和限流。
- 其余 `/api/v1/*` 进入 `ApiSecurityMiddleware`。渠道 webhook 改由各平台 `verify_signature` 鉴权（见 CHANNELS/SECURITY）；未配置平台密钥时放行并返回 `signature=skipped`。
- `API_RATE_LIMIT_PER_MINUTE>0` 时，按 token 摘要优先、客户端 IP 兜底限流；超限返回 429（webhook 路径已豁免）。
- Pydantic 校验失败通常返回 422；路由按业务返回 400/401/404/409/429/500/503。

### 1.3 常用模型

- `ChatRequest`：`message`、`thread_id?`、`agent_id?`、`source=user`、`lang?`；`attachments[]`（内联 Base64，兼容旧客户端）或 `attachment_ids[]`（推荐，两阶段上传）；二者不可同时使用。纯附件消息允许 `message=""`。
- `ExecutionRef`：不可变的 `agent_id`、`thread_id`、显式 `checkpoint_ns`、`interrupt_id`、`interrupt_type`；根图 namespace 为 `""`。
- `ChatResponse`：`thread_id`、`trace_id`、`run_id`、`response`、`todos[]`、`message_count`、`interrupted`、`agent_id`，中断时额外返回 `execution_ref` 与 `payload`。
- `TaskCreateRequest`：`title`、`prompt`、`auto_run=true`、`gateway`、`gateway_user`、`metadata`。
- `TaskResponse`：任务 ID、标题、提示词、状态、thread/trace/run、结果、错误、渠道与时间。
- `PlanConfirmRequest`：优先使用完整 `execution_ref`，`decision=approve|reject|edit`、`edited_todos?`；仅唯一的 `default` pending 可用 `thread_id` 兼容一个迁移周期。
- `PlanConfirmResponse`：返回原始 `execution_ref` 及其 `agent_id`、`thread_id`、`interrupt_id`，另含 `resumed`、`decision`、`edited_todos`、`response`、`message_count`。
- `ApprovalResumeRequest`：`approval_id`、完整 `execution_ref`、`decision=approve|reject`；default Agent 可暂用匹配的 `thread_id`，旧缺 ref 审批不可恢复。

## 2. Agent、计划、会话与 Trace

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `POST` | `/api/v1/agent/chat` | 同步对话或 slash command | `ChatRequest` → `ChatResponse`；body `lang` 优先于 `Accept-Language` | FUN-001、FUN-003、FUN-007 |
| `POST` | `/api/v1/agent/chat/stream` | SSE 流式对话 | `ChatRequest` → `text/event-stream`；v1 事件为 `update`、`interrupt`、`command`、`done`、`error` | FUN-002 |
| `POST` | `/api/v1/agent/runs/cancel` | 取消 Agent 运行并等待确认 | `{agent_id,thread_id,run_id?}` → `{cancelled,status,agent_id,thread_id,run_id,detail}`；无匹配 404，已结束/未确认 409 | FUN-002、FUN-007、FUN-082 |
| `POST` | `/api/v1/agent/plan/confirm` | 恢复计划中断 | `PlanConfirmRequest` → `{execution_ref,thread_id,resumed,decision,edited_todos,response,message_count}`；错误/歧义 ref 返回 4xx | FUN-004 |
| `GET` | `/api/v1/agent/plan/history` | 查询计划审计 | query `agent_id=""`,`thread_id=""`,`limit=100` → `{plans:[]}`；可联合筛选 | FUN-005 |
| `GET` | `/api/v1/agent/sessions` | 会话列表与搜索 | query `q=""`,`limit=50`,`include_archived=false`,`archived_only=false` → `{sessions:[]}`（默认隐藏已归档） | FUN-006 |
| `GET` | `/api/v1/agent/sessions/{thread_id}` | 会话详情/恢复数据 | → session JSON；不存在 404 | FUN-006 |
| `GET` | `/api/v1/agent/sessions/{thread_id}/export` | 导出 Markdown | → `text/markdown`；不存在 404 | FUN-006 |
| `POST` | `/api/v1/agent/sessions/{thread_id}/archive` | 归档会话 | → `{thread_id,archived,archived_at}`；不存在 404 | FUN-006 |
| `POST` | `/api/v1/agent/sessions/{thread_id}/unarchive` | 取消归档 | → `{thread_id,archived:false,archived_at:""}`；不存在 404 | FUN-006 |
| `DELETE` | `/api/v1/agent/sessions/{thread_id}` | 删除本地会话历史 | → `{deleted}`；不存在 404；不清理 Trace/checkpoint | FUN-006 |
| `GET` | `/api/v1/agent/tools` | 查看默认管理器工具列表 | → `{tools:[{name,description,source}]}` | FUN-020、FUN-021 |
| `GET` | `/api/v1/agent/trace/{trace_id}` | 按 Trace 查询原始事件 | → `TraceEventResponse[]` | FUN-121 |
| `GET` | `/api/v1/agent/trace/run/{run_id}` | 按 Run 查询原始事件 | → `TraceEventResponse[]` | FUN-121 |

注意：

- 同步和流式对话共用 `prepare_chat()`：统一 thread、严格 Agent resolver、source、body `lang`/`Accept-Language`、slash command 和 trace/run。控制命令不进入 LLM。
- `/plan` 是消息前缀，不是独立路由；同步和流式调用都会去掉前缀并设置规划态。
- SSE v1 的每个 JSON data envelope 均包含 `event`、`data`、`version`、`thread_id`、`agent_id`、`trace_id`、`run_id`。成功、命令或中断后各发一次 `done`；运行错误发 `error` 且不再发 `done`。
- 流式成功和中断各写一轮 session；命令与失败不写 session。前端停止先 abort 本地读取，再调用运行取消 API；SSE 断连时服务端尽力取消并清理对应单进程 run。
- `/stop` 通过请求中的 `agent_id + thread_id` 定位最新活动 run；同 thread 的其他 Agent 不受影响，无活动 run 返回明确命令响应。
- 计划恢复与工具审批使用不同服务；二者只共享底层 graph resume adapter，interrupt type 不可互换。
- 非默认同步调用和 resume 使用同一严格 Agent resolver；未知/已删除 Agent、非 pending ref、同 thread 跨 Agent 伪造 ref 返回明确 4xx，不回退 default。

## 2.1 附件（两阶段上传）

| 方法 | 完整路径 | 用途 | 主要请求/响应 |
|---|---|---|---|
| `POST` | `/api/v1/agents/{agent_id}/attachments` | 上传附件（multipart：`file`、`relative_path?`） | → 附件元数据；状态 `uploaded → parsing → ready/failed` |
| `GET` | `/api/v1/agents/{agent_id}/attachments` | 列出当前 Agent 附件 | → `{attachments:[]}` |
| `GET` | `/api/v1/agents/{agent_id}/attachments/{attachment_id}` | 查询元数据/解析状态 | 跨 Agent 访问 404 |
| `GET` | `/api/v1/agents/{agent_id}/attachments/{attachment_id}/content` | 结构摘要与文本块 | `{attachment, chunks[]}` |
| `POST` | `/api/v1/agents/{agent_id}/attachments/{attachment_id}/retry` | 失败解析重试 | → 更新后的元数据 |
| `POST` | `/api/v1/agents/{agent_id}/attachments/{attachment_id}/cancel` | 取消上传/解析并删除 | → tombstone |
| `DELETE` | `/api/v1/agents/{agent_id}/attachments/{attachment_id}` | 删除附件与解析产物 | → `{deleted:true}` |

约定：

- 附件按 Agent 隔离存储于 `workspace/attachments/{agent_id}/{attachment_id}/`；记录 SHA-256、MIME、签名校验、`scan_status=unscanned`（无扫描引擎时不伪装为已扫描）。
- 聊天请求优先传 `attachment_ids`；服务端按关键词检索相关文本块注入模型上下文，Trace 记录块 ID/位置/截断信息，不记录原始二进制。
- 会话历史仅保存附件 ID 与摘要行，不保存完整解析文本。

## 3. Console 身份认证

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/auth/status` | 查询是否需要登录及当前 Token 状态 | Header/cookie 可带 Token → `{login_required,authenticated,expires_in_minutes}` | FUN-064、FUN-066 |
| `POST` | `/api/v1/auth/login` | Console 密码登录 | `{password}` → `{login_required,authenticated,token,expires_in_minutes}`，并写 HttpOnly cookie；错误密码 401 | FUN-066 |
| `POST` | `/api/v1/auth/logout` | 清理 Console cookie | → `{authenticated:false}` | FUN-066 |

## 4. 后台任务

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `POST` | `/api/v1/tasks` | 创建任务并可自动运行 | `TaskCreateRequest` → `TaskResponse` | FUN-080 |
| `GET` | `/api/v1/tasks` | 任务列表 | query `status?=pending|running|cancelling|completed|failed|cancelled` → `TaskResponse[]` | FUN-080 |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情 | → `TaskResponse`；不存在 404 | FUN-080 |
| `POST` | `/api/v1/tasks/{task_id}/run` | 重跑任务 | 无 body → 当前 `TaskResponse`；运行中 409 | FUN-081 |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | 取消底层协程并等待确认 | 无 body → cancelled `TaskResponse`；重复取消幂等，completed/failed 返回 409 | FUN-082 |

任务运行使用单进程 `RunRegistry`；pending/running/cancelling/cancelled/completed/failed 转换受限，cancelled 不会被完成/失败回写覆盖。注册表不提供跨进程、多副本或服务重启后的活动运行取消。

## 5. Cron 与 Heartbeat

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/tasks/cron` | Cron Job 列表 | → `{jobs: CronJob[]}` | FUN-084 |
| `POST` | `/api/v1/tasks/cron` | 新建 Cron Job | `{name,cron,prompt,channel?,chat_id?,agent_id?,enabled?}` → CronJob；非法 cron 400 | FUN-084 |
| `PUT` | `/api/v1/tasks/cron/{job_id}` | 更新 Job | 全部字段可选：`name,cron,prompt,channel,chat_id,agent_id,enabled` → CronJob | FUN-084 |
| `DELETE` | `/api/v1/tasks/cron/{job_id}` | 删除 Job | → `{deleted}`；不存在 404 | FUN-084 |
| `POST` | `/api/v1/tasks/cron/{job_id}/enable` | 启停 Job | `{enabled:boolean}` → CronJob | FUN-084 |
| `POST` | `/api/v1/tasks/cron/{job_id}/trigger` | 手动触发启用的 Job | → CronRunRecord；不存在或禁用 404 | FUN-084、FUN-085 |
| `GET` | `/api/v1/tasks/cron/history` | 查询运行历史 | query `job_id=""`,`limit=100` → `{history:[]}` | FUN-085 |
| `GET` | `/api/v1/tasks/heartbeat` | Heartbeat 当前配置 | → `{enabled,interval_minutes,prompt,...}` | FUN-086 |
| `PUT` | `/api/v1/tasks/heartbeat` | 更新 Heartbeat 并持久化/热重调度 | `{enabled?,interval_minutes?,prompt?}` → 当前配置（含 `persisted`） | FUN-086 |

Cron 使用 UTC。Job 配置落盘于 `cron_jobs.json`；运行历史落盘于 `cron_history.json`（上限 500）。Heartbeat PUT 写入 `.env` 的 `HEARTBEAT_*` 并重调度。

## 6. Agent Workspace

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/agents` | Workspace 列表 | 扫描 `agents_root`（跳过 `.deleted`），保证 default 在册；→ `{agents:[{agent_id,root,created_at,loaded,skills_count,config}]}` | FUN-045 |
| `POST` | `/api/v1/agents` | 创建 Workspace 注册项 | `{agent_id,config={}}` → WorkspaceInfo；清除既有 tombstone/purge 标记 | FUN-045 |
| `GET` | `/api/v1/agents/{agent_id}` | Workspace 详情 | 可发现磁盘未加载工作区；tombstone/purge 后 404 | FUN-045 |
| `GET` | `/api/v1/agents/{agent_id}/files` | files 目录索引 | → `{agent_id,root,files:[{path,size,modified_at}]}` | FUN-048 |
| `GET` | `/api/v1/agents/{agent_id}/history` | 聚合任务和会话历史 | query `limit=50` → `{agent_id,history:[]}` | FUN-048 |
| `DELETE` | `/api/v1/agents/{agent_id}` | 注销或彻底清除 | query/body `purge=false|true`；default 400 | FUN-047 |

- `purge=false`（默认）：写 `.deleted` tombstone，保留目录与 checkpoint；列表不可见；resume 409（不可恢复）。
- `purge=true`：删除工作区目录，经 `CheckpointProvider.purge` 清理该 Agent checkpoint，并写 `.purged/{id}` 标记；resume 409。

## 7. Skills

`scope` 仅允许 `pool` 或 `workspace`；工作区接口通过 query `agent_id` 选择 Agent。

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/skills` | 技能池与工作区技能 | query `agent_id=default` → `{pool:[],workspace:[]}` | FUN-040、FUN-041 |
| `POST` | `/api/v1/skills/install` | 从服务器目录安装到技能池 | `{name,source_dir,overwrite=false}` → SkillInfo | FUN-040 |
| `GET` | `/api/v1/skills/{scope}/{name}` | 技能详情、文件列表和扫描结果 | query `agent_id` → `{info,files,scan}` | FUN-042、FUN-043 |
| `GET` | `/api/v1/skills/{scope}/{name}/file` | 读取技能文本文件 | query `path=SKILL.md`,`agent_id` → `{path,content}` | FUN-042 |
| `PUT` | `/api/v1/skills/{scope}/{name}/file` | 写技能文本文件 | query `agent_id`；body `{path,content}` → `{path,info}` | FUN-042 |
| `DELETE` | `/api/v1/skills/{scope}/{name}` | 删除池或工作区技能 | query `agent_id` → `{deleted,scope}` | FUN-042 |
| `GET` | `/api/v1/skills/{scope}/{name}/scan-report` | 重新生成扫描报告 | query `agent_id` → `{safe,findings}` | FUN-043 |
| `POST` | `/api/v1/skills/{name}/enable` | 启停工作区技能 | query `agent_id=default`；body `{enabled=true}` → `{name,enabled}` | FUN-041 |
| `POST` | `/api/v1/skills/{name}/add-to-workspace` | 从池复制到 Workspace | query `agent_id=default` → SkillInfo | FUN-041 |
| `POST` | `/api/v1/skills/scan` | 扫描任意给定服务器目录 | `{path}` → `{safe,findings}` | FUN-043 |
| `POST` | `/api/v1/skills/reload` | 重建 Agent 使技能生效 | body 可省略或 `{agent_id?}` → `{reloaded,agents}` | FUN-044 |

## 8. Provider 与模型连接

`name` 兼容值为 `openai`、`anthropic`、`ollama`；新连接使用 `conn_*` ID。API Key 经 AES-256-GCM 保险箱存储，需 `BOETCLAW_MASTER_KEY`（32 字节，仅环境变量）。

### 8.1 兼容 Provider 路由

| 方法 | 完整路径 | 用途 | 主要请求/响应 |
|---|---|---|---|
| `GET` | `/api/v1/providers` | Provider 类型列表 | → `{providers:[]}` |
| `GET` | `/api/v1/providers/config` | 当前默认 | → `{provider,model,connection_id?}` |
| `PUT` | `/api/v1/providers/default` | 修改默认（不写 API Key 到 `.env`） | `{provider,model}` |
| `GET` | `/api/v1/providers/{name}/config` | 非敏感状态（无密钥回填） | 含 `credential_source`、`credential_fingerprint` |
| `PUT` | `/api/v1/providers/{name}/config` | 保存至保险箱 | `{api_key?,base_url?}` |
| `GET` | `/api/v1/providers/{name}/models` | 模型列表 | → `{models:[]}` |
| `POST` | `/api/v1/providers/{name}/check` | 连通性检查 | 脱敏结果 |

### 8.2 模型连接 API

| 方法 | 完整路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/provider-connections/vault/status` | 保险箱状态 |
| `GET` | `/api/v1/provider-connections` | 连接列表 |
| `POST` | `/api/v1/provider-connections` | 创建（`validate_only` 可选） |
| `PUT` | `/api/v1/provider-connections/{id}` | 更新（revision 冲突 409） |
| `DELETE` | `/api/v1/provider-connections/{id}` | 删除（被引用 409） |
| `POST` | `/api/v1/provider-connections/{id}/check` | 检测 |
| `POST` | `/api/v1/provider-connections/{id}/set-default` | 设为默认 |
| `POST` | `/api/v1/provider-connections/import-env` | 显式导入环境变量（提示手动清理 `.env`） |

更新默认值不会显式重建所有已创建 Agent；进行中的运行保持连接快照。

## 9. ToolGuard 与审批

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/security/config` | Guard 当前开关和级别 | → `{enabled,level}` | FUN-060 |
| `PUT` | `/api/v1/security/config` | 修改运行时 Guard 级别 | `{level}` → `{enabled,level}` | FUN-060 |
| `GET` | `/api/v1/security/approvals` | 需关注审批列表 | → `{pending: ApprovalRequest[]}`；包含 pending/resuming/resume_failed/expired | FUN-062 |
| `GET` | `/api/v1/security/approvals/history` | 全部审批历史 | → `{approvals: ApprovalRequest[]}` | FUN-063 |
| `POST` | `/api/v1/security/approvals/resume` | 校验并恢复工具审批 | `{approval_id,execution_ref,decision}` → `{resumed,decision,approval,execution_ref,result}`；旧 default thread-only 有限兼容 | FUN-062 |

Guard 级别更新只修改运行时 settings，当前路由没有把它写回 `.env`。
审批记录包含可选 `execution_ref`、`idempotency_key`、`status`、`decision`、`error` 和更新时间。`approval_id` 只接受 1—128 位字母、数字、`_`、`-`；服务端还会逐项校验记录存在、完整 ref 相等、interrupt type 为 `tool_approval`、状态为 pending 及 decision 为 approve/reject。裁决先原子进入 `resuming`，只有 graph 成功才写 `approved/rejected`；运行异常写不可自动重试的 `resume_failed`。旧 JSON 缺 ref 时仍可查询但裁决返回 409。

## 10. Tools 与 MCP

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/tools` | 工具汇总 | → `{builtin,mcp,total}` | FUN-020、FUN-021 |
| `GET` | `/api/v1/tools/mcp/servers` | MCP 服务器状态 | → `{servers:[]}` | FUN-023 |
| `GET` | `/api/v1/tools/mcp/tools` | MCP 工具及参数详情 | → `{tools:[]}` | FUN-023 |
| `GET` | `/api/v1/tools/mcp/tools/{name}` | 单个 MCP 工具详情 | → tool detail；不存在 404 | FUN-023 |
| `POST` | `/api/v1/tools/mcp/reload` | 重连 MCP 并重建默认 Agent 工具 | 无 body → `{status,tools,mcp_tools,servers,mcp_tool_details}` | FUN-023 |

## 11. Plugins 与 Commands

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/plugins` | 已发现插件列表 | → `{plugins:[]}` | FUN-024、FUN-025 |
| `POST` | `/api/v1/plugins/reload` | 重新发现/加载插件 | 无 body → `{reloaded,plugins}` | FUN-025 |
| `POST` | `/api/v1/plugins/scan` | 按路径静态安全扫描（复用 SkillScanner） | `{path}` → `{safe,findings}` | FUN-025、REQ-125 |
| `POST` | `/api/v1/plugins/install` | 从服务器目录复制安装；安装前扫描，不安全则 400 | `{name,source_dir,overwrite=false}` → PluginInfo；失败 `{message,safe,findings}` | FUN-025、REQ-125 |
| `GET` | `/api/v1/plugins/{name}` | 插件详情、manifest 与扫描摘要 | → PluginInfo + `manifest` + `scan` | FUN-025 |
| `GET` | `/api/v1/plugins/{name}/scan-report` | 重新生成扫描报告 | → `{safe,findings}` | FUN-025、REQ-125 |
| `PUT` | `/api/v1/plugins/{name}/enabled` | 启停插件并写 `ENABLED_PLUGINS` | `{enabled}` → PluginInfo | FUN-025 |
| `DELETE` | `/api/v1/plugins/{name}` | 删除插件目录，移出 `ENABLED_PLUGINS` 并 reload | → `{deleted}`；不存在 404；路径穿越 400 | FUN-025 |
| `GET` | `/api/v1/commands` | Slash 命令元数据 | → `{commands:[]}` | FUN-007 |

## 12. Gateway

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/gateway/platforms` | 已注册渠道名 | → `{platforms:[]}` | FUN-087 |
| `GET` | `/api/v1/gateway/status` | 配置、队列等运行状态 | → `{channels:[]}` | FUN-089 |
| `GET` | `/api/v1/gateway/access-control` | 获取各渠道 allowed_users | → access-control JSON | FUN-067 |
| `PUT` | `/api/v1/gateway/access-control` | 更新白名单 | `{channels:{platform:{allowed_users:[...]}}}` → 更新结果 | FUN-067 |
| `GET` | `/api/v1/gateway/messages` | 消息审计历史 | query `platform=""`,`status=""`,`limit=100` → `{messages:[]}` | FUN-089 |
| `POST` | `/api/v1/gateway/messages/{record_id}/retry` | 重试当前进程中可恢复的失败消息 | 无 body → `{retried}`；不可重试 404 | FUN-089 |
| `POST` | `/api/v1/gateway/dingtalk/webhook` | 钉钉入口；校验 `timestamp`/`sign` | 平台 JSON → `GatewayWebhookResponse`（含 `signature`）；验签失败 401 | FUN-087、FUN-088 |
| `POST` | `/api/v1/gateway/feishu/webhook` | 飞书入口及 URL verification；校验 token | 平台 JSON → challenge 或 webhook 响应；验签失败 401 | FUN-087、FUN-088 |
| `POST` | `/api/v1/gateway/qq/webhook` | QQ/OneBot 入口；Bearer 或 `X-Signature` | 平台 JSON → `GatewayWebhookResponse`；验签失败 401 | FUN-087、FUN-088 |
| `POST` | `/api/v1/gateway/telegram/webhook` | Telegram 入口；校验 secret token 头 | 平台 JSON → `GatewayWebhookResponse`；验签失败 401 | FUN-087、FUN-088 |
| `POST` | `/api/v1/gateway/{platform}/webhook` | 通用已注册渠道入口（同上验签） | 平台 JSON → `GatewayWebhookResponse`；未配置 503；验签失败 401 | FUN-087、FUN-088 |

响应 `success=true` 也可能表示 `Ignored`、`Denied by access control` 或 `Rate limited`；调用方应检查 `message`。

## 13. 钻井领域

### 13.1 井

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/domain/wells` | 井列表 | → `Well[]` | FUN-100 |
| `POST` | `/api/v1/domain/wells` | 新建井 | `{name,field?,operator?,location?,status?,metadata?}` → `Well` | FUN-100 |
| `GET` | `/api/v1/domain/wells/{well_id}` | 井详情 | → `Well`；不存在 404 | FUN-100 |
| `PUT` | `/api/v1/domain/wells/{well_id}` | 更新井 | `WellIn` → `Well` | FUN-100 |
| `DELETE` | `/api/v1/domain/wells/{well_id}` | 删除井 | → `{deleted}`；存在井段/日报/参数/LAS/产物依赖时 409 | FUN-100、FUN-106 |

### 13.2 井段、日报和参数

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/domain/sections` | 井段列表 | query `well_id=""` → `WellboreSection[]` | FUN-101 |
| `POST` | `/api/v1/domain/sections` | 新建井段 | `{well_id,name,top_depth?,bottom_depth?,hole_size?,start_date?,end_date?}` → 井段 | FUN-101 |
| `GET` | `/api/v1/domain/sections/{section_id}` | 井段详情 | → 井段；不存在 404 | FUN-101 |
| `PUT` | `/api/v1/domain/sections/{section_id}` | 更新井段 | `SectionIn` → 井段 | FUN-101 |
| `DELETE` | `/api/v1/domain/sections/{section_id}` | 删除井段 | → `{deleted}` | FUN-101 |
| `GET` | `/api/v1/domain/reports` | 日报列表 | query `well_id=""` → `DailyReport[]` | FUN-102 |
| `POST` | `/api/v1/domain/reports` | 新建日报 | `{well_id,report_date,depth_start?,depth_end?,summary?,issues?}` → 日报 | FUN-102 |
| `GET/PUT/DELETE` | `/api/v1/domain/reports/{report_id}` | 日报详情、全量更新、删除 | `DailyReportIn` → 日报；删除 → `{deleted}` | FUN-102 |
| `GET` | `/api/v1/domain/params` | 钻井参数列表 | query `well_id=""` → `DrillingParam[]` | FUN-103 |
| `POST` | `/api/v1/domain/params` | 新建参数 | `{well_id,measured_depth,timestamp?,wob?,rpm?,rop?,torque?,pump_pressure?,flow_rate?,source?}` → 参数 | FUN-103 |
| `GET/PUT/DELETE` | `/api/v1/domain/params/{param_id}` | 参数详情、全量更新、删除 | `DrillingParamIn` → 参数；删除 → `{deleted}` | FUN-103 |

### 13.3 LAS

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/domain/las-files` | LAS 记录列表 | query `well_id=""` → `LasFile[]` | FUN-104 |
| `POST` | `/api/v1/domain/las-files` | 直接登记 LAS 元数据 | `LasFileIn` → `LasFile` | FUN-104 |
| `GET/PUT/DELETE` | `/api/v1/domain/las-files/{las_id}` | LAS 详情、全量更新、删除 | 删除返回托管文件清理结果；外部源文件保留 | FUN-104、FUN-106 |
| `POST` | `/api/v1/domain/las/import` | 从服务器路径解析导入 | `{well_id,path,filename?}` → `LasFile`；文件不存在 404 | FUN-105 |
| `POST` | `/api/v1/domain/las/upload` | 上传并解析/质检 LAS | `multipart/form-data`: `well_id`、`file`、`filename?` → `LasFile`；非 `.las` 400，超 `LAS_UPLOAD_MAX_BYTES` 413，缺 LAS 段标记 400 | FUN-105 |

关联写入的 `well_id` 不存在时返回 404，`detail.code=well_not_found`。删除有关联数据的井返回 409，`detail.code=well_has_dependencies` 并在 `dependencies` 中给出非零计数。领域 JSON 新写入带 `schema_version=1`，旧无版本文件可直接读取；单实例写入采用进程内锁、写前 `.bak` 和同目录原子替换。

## 14. 文件与产物

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/files/artifacts` | 产物列表与筛选 | query `kind=""`,`well_id=""`,`agent_id=""` → `{artifacts:[...,sha256]}` | FUN-109 |
| `GET` | `/api/v1/files/artifacts/{kind}/{filename}/download` | 下载 chart/code | → `FileResponse`；kind 非法 400 | FUN-109 |
| `DELETE` | `/api/v1/files/artifacts/{kind}/{filename}` | 删除 chart/code 产物 | → `{deleted,kind}`；同步删除 sidecar metadata；不存在 404 | FUN-109 |
| `GET` | `/api/v1/files/{filename}` | 读取图表 PNG | → `image/png` | FUN-107、FUN-109 |
| `GET` | `/api/v1/files/code/{filename}` | 读取代码文本 | → `text/plain` | FUN-107、FUN-109 |

文件名经过根目录约束，阻止 `..` 越界。产物列表仅识别 charts 下 PNG 和 code 下普通文件并返回 SHA256；删除只清理产物文件与 metadata，不清理 Trace 或任务记录。

## 15. 监控

| 方法 | 完整路径 | 用途 | 主要请求/响应 | 功能 |
|---|---|---|---|---|
| `GET` | `/api/v1/monitor/health` | 应用、Agent 与 checkpoint 探活 | → `status,ready,agent_ready,checkpoint`；checkpoint 含 backend/persistent/supports_restart_resume/warning/error；免鉴权限流 | FUN-122、FUN-127 |
| `GET` | `/api/v1/monitor/stats` | JSON 运行统计 | → 任务状态、事件、审批、队列等聚合 | FUN-122 |
| `GET` | `/api/v1/monitor/metrics` | Prometheus text exposition | → `text/plain; version=0.0.4` | FUN-123 |
| `GET` | `/api/v1/monitor/events` | 最近 Trace 事件 | query `limit=100` → `TraceEventResponse[]`，新到旧 | FUN-120 |
| `GET` | `/api/v1/monitor/trace/{trace_id}/timeline` | 结构化时间线 | → `{trace_id,event_count,started_at,ended_at,duration_ms,categories,events}`；无事件 404 | FUN-121 |

Metrics 覆盖任务状态、Trace/事件类型、审批、渠道队列、MCP recover、Agent/工具/Guard/Provider 计数及 Agent 运行耗时 histogram。

## 16. 调用示例

同步计划：

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d '{"message":"/plan 生成 XX-1 井日报并绘图","thread_id":"demo","agent_id":"default","source":"user"}'
```

确认计划：

```bash
curl -X POST http://localhost:8000/api/v1/agent/plan/confirm \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d '{"execution_ref":{"agent_id":"default","thread_id":"demo","checkpoint_ns":"","interrupt_id":"<服务端返回值>","interrupt_type":"plan_confirm"},"decision":"approve"}'
```

上传 LAS：

```bash
curl -X POST http://localhost:8000/api/v1/domain/las/upload \
  -H "Authorization: Bearer $API_TOKEN" \
  -F "well_id=well-id" \
  -F "file=@sample.las"
```

## 17. 契约维护规则

1. 新增或修改路由时，先保证 Pydantic/FastAPI schema 正确出现在 `/docs`。
2. 本文路径必须写完整 `/api/v1` 前缀，避免与前端相对调用混淆。
3. 本文不复制 OpenAPI 的每个字段约束；字段细节始终以运行时 `/docs` 为准。
4. 若代码行为与本文不一致，应先按代码和运行时 OpenAPI 判定事实，再修正文档。
