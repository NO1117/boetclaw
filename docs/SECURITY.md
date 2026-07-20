# 安全说明

> 文档基线：2026-07-16。

本文描述当前代码已经实现的控制及其边界，不构成安全认证。主要事实来源为
`backend/app/security/`、`backend/app/middleware/`、`backend/app/services/gateway/`、
`backend/app/skills_system/scanner.py`、`backend/app/plugins/loader.py` 和对应测试。

## ToolGuard

`ToolGuardMiddleware` 在 Agent 工具调用前执行 `ToolGuardEngine`。引擎依次合并三个 guardian 的结果：

- `RuleBasedToolGuardian`：拒绝 `TOOL_GUARD_DENIED_TOOLS` 中的工具；把
  `execute_shell_command`、`execute`、`delete` 标记为高风险，把 `write_file`、
  `edit_file` 标记为中风险。
- `FilePathToolGuardian`：检查常见路径参数，命中 `FILE_GUARD_DENY_DIRS` 时硬拒绝。
- `ShellEvasionGuardian`：仅对指定 Shell 工具检查 `rm -rf`、`curl|sh`、命令替换、
  `mkfs`、`dd`、块设备写入等正则模式，命中时硬拒绝。

```env
TOOL_GUARD_ENABLED=true
TOOL_GUARD_LEVEL=smart
TOOL_GUARD_DENIED_TOOLS=
FILE_GUARD_DENY_DIRS=.env,.git,.ssh,.qwenpaw.secret
```

策略语义以 `backend/app/security/engine.py` 为准：

- `strict`：所有未被硬拒绝的工具调用都要求审批，并非全部直接阻断。
- `smart`：严重度达到 medium 的发现要求审批；默认值。
- `auto`：只保留 guardian 已标记且达到 high 的审批要求；硬拒绝仍生效。
- `off` 或 `TOOL_GUARD_ENABLED=false`：直接允许，不运行上述策略。
- 显式拒绝、敏感路径和危险 Shell 模式属于硬拒绝，在启用状态下优先于策略级别。

ToolGuard 是工具名、参数键和正则驱动的应用层控制，不是 OS 沙箱。未知工具名、参数嵌套、
编码/混淆、符号链接或规则未覆盖的危险行为可能绕过检测。

## ToolGuard 审批与持久化

需要审批时，中间件会：

1. 按服务端 `agent_id + thread_id + tool_call_id` 稳定 key 幂等创建或复用 `ApprovalRequest`；
2. 调用 LangGraph `interrupt()` 暂停；
3. 由 `/api/v1/security/approvals` 和
   `/api/v1/security/approvals/resume` 提供查询与恢复入口。

审批历史默认写入：

```text
backend/workspace/security/approval_history.json
```

实际位置跟随 `WORKSPACE_DIR`。新记录包含工具名、原始参数、发现、稳定 key、完整 `ExecutionRef`、状态、裁决、错误和时间，因此可能包含敏感内容；
文件未加密。服务重启时，历史中仍为 `pending` 的记录保持 pending；系统不会自动批准或继续执行，
只有携带完整 `ExecutionRef` 的显式裁决才会尝试恢复。

需要注意：

- `ExecutionRef` 由后端从真实 LangGraph Interrupt 生成，包含 Agent、thread、显式 checkpoint namespace、interrupt ID/type；前端只保存并回传，不猜测运行身份。
- 默认使用 `langgraph-checkpoint-sqlite==3.1.0` 的 `AsyncSqliteSaver`，每个 Agent 独立数据库；进程或 Agent 重建后，adapter
  按服务端 `ExecutionRef` 解析原 Agent，并核对 SQLite 中相同 interrupt ID 后恢复。
- checkpoint/原 Agent 不存在、interrupt 已完成或旧 JSON 缺 `execution_ref` 时返回 409，不会把
  审批历史伪装成 checkpoint，也不会自动批准。显式 memory 模式不支持跨重启并在 health 中告警。
- `ToolGuardMiddleware` 创建记录或 `interrupt()` 失败会 fail-closed：异常继续上抛，受保护 handler 不执行，不再存在自动 approve。
- LangGraph resume 从节点开头重放；中间件会复用相同稳定 key 的 pending/resuming 审批，不重复创建 pending。
- `/security/approvals/resume` 使用独立审批恢复服务，恢复前校验 approval ID、pending、完整 ref、interrupt type、decision 及记录一致性；错误请求返回明确 4xx 且不调用 graph。
- 裁决在进程内互斥锁下先从 `pending` 原子进入 `resuming`；重复或并发请求不能再次进入 graph。graph resume 成功后才写 `approved/rejected`；运行异常或处理中服务重启写 `resume_failed` 与错误摘要，并作为不可自动重试终态。
- 旧 JSON 缺 `execution_ref` 时仍可查看，但 API 与前端均禁止恢复。
- checkpoint 数据可能包含对话、工具参数和中断 payload，应与审批 JSON 一样按敏感数据保护、限制权限并加密备份。
- PLAN-120 专项测试使用真实最小 LangGraph interrupt/resume 验证 approve handler 一次、reject 零次、节点重放不重复审批、重复/并发裁决不重复、SQLite 重建恢复和非默认 Agent resolver；完整多 Agent 计划 API E2E 仍属于 PLAN-130。
- SQLite 仅提供单机 checkpoint；审批 JSON、checkpoint 与工具外部副作用没有跨资源事务。进程若在副作用完成后、graph 或审批终态写回前崩溃，系统无法可靠判断副作用是否发生，只能将不确定恢复置为不可自动重试。不得宣称本实现提供分布式 exactly-once。

## Plan Gate

`PlanGateMiddleware` 使用状态字段 `plan_phase`：

- `planning` 阶段仅允许 `write_todos`，其他工具返回错误。
- 在 `planning` 或 `idle` 阶段调用 `write_todos` 后，先执行该工具，再调用
  LangGraph `interrupt()` 请求计划确认。
- 计划确认、编辑及失败历史有后端测试，但这仍是 Agent 工作流控制，不是权限边界。
- 在图外 `interrupt()` 失败时异常上抛，不再伪装为可靠暂停。

## API Token 与 Console JWT

`ApiSecurityMiddleware` 只保护 `/api/v1` 路径。以下规则需要同时理解：

- `API_TOKEN` 和 `CONSOLE_PASSWORD` 都为空时，API 默认开放，适合可信本地开发，不适合公网。
- API Token 支持 `Authorization: Bearer <token>` 或 `X-API-Token`。
- 设置 `CONSOLE_PASSWORD` 后，`POST /api/v1/auth/login` 返回 HMAC-SHA256 签名的 JWT，
  同时写入 `boetclaw_console_token` HttpOnly、SameSite=Lax Cookie。
- JWT 密钥按 `CONSOLE_JWT_SECRET`、`API_TOKEN`、`CONSOLE_PASSWORD` 的顺序回退；
  生产环境应设置独立、随机且足够长的 `CONSOLE_JWT_SECRET`。
- JWT 默认有效期由 `CONSOLE_JWT_TTL_MINUTES=480` 控制；当前没有服务端撤销列表，
  logout 只删除客户端 Cookie。
- `/api/v1/auth/*`、`/api/v1/monitor/health` 以及 `/api/v1/gateway/*/webhook` 绕过中间件鉴权
  （与限流）。Webhook 依赖各渠道平台验签，见下文。
- `/docs`、`/openapi.json`、`/ui/` 和根路径不在 `/api/v1` 下，因此该中间件不保护它们。
- Cookie 当前未设置 `Secure` 属性。公网部署必须终止 HTTPS，并应评估在代码或代理层补强 Cookie 策略。

建议生产配置：

```env
API_TOKEN=<独立随机长令牌>
CONSOLE_PASSWORD=<独立强密码>
CONSOLE_JWT_SECRET=<独立随机长密钥>
CONSOLE_JWT_TTL_MINUTES=60
```

## 限流

存在三类进程内滑动窗口限流：

- `API_RATE_LIMIT_PER_MINUTE`：按 API/Console token 的 SHA-256 摘要分桶，无 token 时按客户端 IP。
- `GATEWAY_RATE_LIMIT_PER_MINUTE`：按“渠道 + user_id（无 user_id 时 chat_id）”分桶。
- `PROVIDER_RATE_LIMIT_PER_MINUTE`：按 provider/model 分桶。

值为 `0` 时关闭。状态只存在单个 Python 进程内，重启会清空，多 worker/多副本之间不共享，
不能替代 nginx/API gateway/Redis 等集中式限流。

## 渠道白名单与 webhook

渠道访问控制保存在 `WORKSPACE_DIR/access_control.json`。每个渠道的 `allowed_users` 为空或缺失时
默认开放；非空时按解析后的字符串 `user_id` 精确匹配。公网启用渠道前应显式设置非空白名单。

### 两层鉴权（API Token vs 平台验签）

1. **HTTP API 层**：`ApiSecurityMiddleware` 保护管理类 `/api/v1/*`。  
   `POST /api/v1/gateway/*/webhook` **豁免**该层，以便平台回调在配置了 `API_TOKEN` 时仍可达。
2. **平台 webhook 层**：`_handle_webhook` 在解析业务 JSON 前调用 `verify_signature(headers, body)`。

| 渠道 | 配置项 | 校验方式 |
|---|---|---|
| 钉钉 | `DINGTALK_WEBHOOK_SECRET` | 头 `timestamp` + `sign`，HMAC-SHA256 |
| 飞书 | `FEISHU_VERIFICATION_TOKEN` | body `token` 或 v2 `header.token` |
| QQ | `QQ_WEBHOOK_SECRET` | `Authorization: Bearer` 或 `X-Signature: sha1=` |
| Telegram | `TELEGRAM_WEBHOOK_SECRET` | `X-Telegram-Bot-Api-Secret-Token` |

未配置对应密钥时放行并标记 `signature=skipped`（适合本地开发，**不适合公网**）。配置后校验失败返回 401。
飞书加密事件、时间戳窗口/重放防护未实现；公网仍应配合 HTTPS 与来源约束。

## 技能与插件

`SkillScanner` 对指定扩展名文件做正则扫描，可发现部分 OpenAI/AWS/GitHub 密钥、
硬编码 password/secret，以及 `os.system`、`subprocess`、`eval`、`exec`、动态 import、
`rm -rf` 等模式。它是静态提示工具，存在误报和漏报，不能证明技能或插件安全。

插件目录默认为 `backend/plugins_ext/`。`POST /api/v1/plugins/install` 在复制前复用同一
`SkillScanner`；发现风险则拒绝安装且不写入 `ENABLED_PLUGINS`。磁盘上的插件只有名字列入
`ENABLED_PLUGINS` 时才会动态 import 并注册工具；`DELETE /api/v1/plugins/{name}` 会删除目录
并同步更新启用列表：

```env
ENABLED_PLUGINS=
```

插件导入发生在后端进程内，没有进程、容器、文件系统或网络沙箱；启用插件等价于信任其 Python
代码。上线前应固定来源和版本、人工审查、最小化容器权限，并在隔离环境验证。

## 其他边界与生产要求

- `source="cron"` 和 `source="heartbeat"` 默认不写长期记忆，可降低自动任务污染，但不是内容安全过滤。
- `backend/.env`、workspace 中的审批/消息/任务历史和 provider 凭据都应按敏感数据保护。
- 收紧 `CORS_ORIGINS`，不要保留不需要的开发源。
- 对外仅暴露必要路径；限制 `/docs`、`/openapi.json`、管理 API 和 `/ui/` 的访问。
- 保持 `TOOL_GUARD_ENABLED=true`，不要把 `off` 用于生产。
- 使用非 root、只读根文件系统、最小挂载和出站网络控制；当前 Dockerfile 本身未声明非 root 用户。
- 备份 workspace 时同步实施访问控制、加密、保留期和安全删除。
- CI 已含 `pip-audit`、`npm audit`（high+）与可选 gitleaks（默认非阻断）；镜像 CVE 扫描与专项安全 E2E 仍未做阻断门禁。
