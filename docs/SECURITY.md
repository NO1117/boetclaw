# 安全说明

> 文档基线：2026-07-28。

本文描述当前代码已经实现的控制及其边界，不构成安全认证。主要事实来源为
`backend/app/security/`、`backend/app/middleware/`、`backend/app/credentials/`、
`backend/app/providers/connections/`、`backend/app/services/gateway/`、
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

## API Token、团队身份与 Console 会话

`ApiSecurityMiddleware` 只保护 `/api/v1` 路径。当前身份模型为**单实例、单工作区、多用户**：

- 无用户且未配置 `API_TOKEN`/`CONSOLE_PASSWORD` 时为开放模式（可信本地开发）。
- 空用户库可通过本机或 `BOOTSTRAP_TOKEN` 调用 `POST /api/v1/auth/bootstrap` 创建首个 owner。
- 用户密码使用 Argon2id；会话 JWT 含 `user_id/role/token_version/session_id`，服务端 SQLite WAL 持久化会话，支持撤销与 token version 失效。
- Cookie：`boetclaw_console_token`（HttpOnly、SameSite=Lax；生产可设 `CONSOLE_COOKIE_SECURE=true`）+ CSRF（`boetclaw_csrf` / `X-CSRF-Token`）。Bearer/API Token 写请求不校验 Cookie CSRF。
- `API_TOKEN` 兼容为受审计的 legacy service principal（admin 级，不可管理 owner / 读取凭据明文）。
- `CONSOLE_PASSWORD` 仍可作为兼容登录；owner 创建后 UI 提示停用，不自动改 `.env`。
- 系统角色：`owner` / `admin` / `operator` / `viewer`；Agent/知识库支持 `private|workspace` 与 `viewer|editor|runner` 授权。无权限资源统一 404。
- 身份库默认路径：`workspace/identity/identity.sqlite3`（WAL）；审计不记录密码/token/全文。

建议生产配置：

```env
API_TOKEN=<独立随机长令牌>
CONSOLE_JWT_SECRET=<独立随机长密钥>
CONSOLE_JWT_TTL_MINUTES=60
CONSOLE_COOKIE_SECURE=true
BOOTSTRAP_TOKEN=<可选，非本机 bootstrap 时必填>
# CONSOLE_PASSWORD=  # 迁移期兼容；团队启用后建议移除
```

`/api/v1/auth/*`、`/api/v1/monitor/health` 以及 `/api/v1/gateway/*/webhook` 绕过中间件鉴权（与限流）。Webhook 依赖各渠道平台验签。
`/docs`、`/openapi.json`、`/ui/` 和根路径不在 `/api/v1` 下，因此该中间件不保护它们。

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

## Provider 凭据保险箱

Provider API Key 可通过控制台写入本地 AES-256-GCM 保险箱（`backend/app/credentials/vault.py`），
并与 Provider 连接配置分离（`backend/app/providers/connections/`）。实现边界如下。

### 威胁边界与保护范围

保险箱提供的是**单机、本地、静态加密存储**，不是云 KMS/HSM、多租户密钥托管或 OS 沙箱。

- **保护对象**：磁盘上的 `workspace/credentials/vault.json` 中的 Provider API Key 密文；损坏文件会隔离到
  `workspace/credentials/quarantine/`。
- **不保护**：运行中的进程内存、已配置主密钥的环境、拥有 workspace 读权限的操作系统用户、
  未清理的 `backend/.env` 明文、容器/备份介质上的副本。攻击者若同时获得 vault 文件与主密钥，可解密全部凭据。
- **算法**：标准 AEAD（AES-256-GCM）；禁止依赖 Base64 伪加密或仓库内固定密钥。
- **文件权限**：写入后尝试 `chmod 600`；仍须限制 workspace 目录的宿主/容器挂载权限。
- **并发与持久化**：原子写入与进程内锁；无跨进程/多副本协调。多实例部署不应共享同一 vault 文件。

### 主密钥（`BOETCLAW_MASTER_KEY`）

主密钥**仅从环境变量**读取（`backend/app/credentials/master_key.py`），不写入仓库、
不通过 API 下发、不持久化到 workspace。

- **格式**：32 字节随机值，以标准或 URL-safe Base64（推荐）或 64 字符 hex 注入。
- **生成**（在可信本机执行，将输出粘贴到部署环境，勿写入 git）：

```powershell
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))"
```

```bash
python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))"
```

- **注入**：本地开发可写入未提交的 `backend/.env`；生产应使用 secrets manager、
  编排器 secret 或受控挂载，并限制仅 backend 进程可读。Docker Compose 通过 `backend/.env`
  注入，**不得**把真实主密钥提交到镜像或版本库。
- **轮换**：在应用运行且当前主密钥可解密的前提下，调用 vault 的 `rotate_master_key(new_key)` 重加密全部记录；
  随后更新环境中的 `BOETCLAW_MASTER_KEY` 并重启进程（或 `clear_master_key_cache()` 后重载）。
  轮换前必须备份 `vault.json`；用错误/旧主密钥启动时解密失败并返回 503，**不会**自动损坏或抹除密文。
- **丢失主密钥**：无法恢复已加密凭据；只能从 Provider 控制台重新签发 API Key 并重新保存，或回退到环境变量凭据。

### 无主密钥降级

未配置 `BOETCLAW_MASTER_KEY` 时：

- 保险箱**写入**（创建/替换连接中的 API Key、显式导入）禁用，API 返回 503 与可操作说明；
- 已存在于 `OPENAI_API_KEY` 等环境变量中的凭据**仍可**用于聊天与连接检测；
- 应用**不会**因此崩溃。生产若需控制台保存密钥，必须配置主密钥。

### 环境变量导入与 `.env` 清理

- 启动时**只读**兼容现有环境变量，**不会**自动改写或删除 `backend/.env`。
- `POST /api/v1/provider-connections/import-env` 为显式一次性导入；成功响应含
  `env_cleanup_required: true` 时，用户须**手动**从 `backend/.env` 删除对应明文 Key
  （如 `OPENAI_API_KEY`）；系统不会伪称已删除。
- 经 `/api/v1/providers/*/config` 保存的 API Key 只写保险箱，**不再**调用 `update_env_file` 写入明文。

### 密钥不进日志 / API / Trace

- 完整 API Key、Authorization 头、密文、nonce、主密钥不得出现在 REST 响应、OpenAPI 示例、
  结构化日志、Trace/审计详情或测试快照中。
- 连接 API 仅返回 `credential_configured`、`credential_source`（`vault` / `env` / `none`）
  及末四位 `credential_fingerprint`（可安全取得时）。
- `backend/app/credentials/redaction.py` 与 observability 事件路径会对常见密钥模式脱敏；
  上游错误若含密钥，仍应视为不可信输入并依赖脱敏层。

### 备份与恢复

- **须一并保护**：`workspace/credentials/vault.json` 与当时有效的 `BOETCLAW_MASTER_KEY`。
  仅有 vault 文件而无主密钥无法解密；仅有主密钥而无 vault 则无法恢复已存连接引用。
- **建议**：备份整个 `workspace/`（含 `provider_connections.json`），加密存储、限制访问、
  定期做恢复演练。恢复后确认 vault 状态 API 与一次连接检测。
- **quarantine**：若 vault JSON 损坏，原文件会移入 quarantine；恢复需运维从备份还原或重建凭据。

```env
# 生产示例：占位，勿提交真实值
BOETCLAW_MASTER_KEY=
```

详见 `docs/API.md` 中 Provider 连接与 `GET /api/v1/provider-connections/vault/status` 索引。

## 其他边界与生产要求

- `source="cron"` 和 `source="heartbeat"` 默认不写长期记忆，可降低自动任务污染，但不是内容安全过滤。
- 任务结果、错误、事件与运行快照经脱敏截断后写入 SQLite；API Key、凭据与完整知识库正文不得进入任务表。
- `backend/.env`、workspace 中的审批/消息/任务队列与历史、`workspace/credentials/` 与 provider 连接配置都应按敏感数据保护。
- 收紧 `CORS_ORIGINS`，不要保留不需要的开发源。
- 对外仅暴露必要路径；限制 `/docs`、`/openapi.json`、管理 API 和 `/ui/` 的访问。
- 保持 `TOOL_GUARD_ENABLED=true`，不要把 `off` 用于生产。
- 使用非 root、只读根文件系统、最小挂载和出站网络控制；当前 Dockerfile 本身未声明非 root 用户。
- 备份 workspace 时同步实施访问控制、加密、保留期和安全删除。
- CI 已含 `pip-audit`、`npm audit`（high+）与可选 gitleaks（默认非阻断）；镜像 CVE 扫描与专项安全 E2E 仍未做阻断门禁。
