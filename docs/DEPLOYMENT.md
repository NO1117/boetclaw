# 部署说明

> 文档基线：2026-07-28。

本文按当前 `scripts/`、`Dockerfile`、`docker-compose.yml`、`deploy/nginx.conf` 和
`backend/app/main.py` 描述部署行为。后端安装脚本明确接受 Python 3.11–3.13，
Docker 后端镜像使用 Python 3.12；前端构建镜像使用 Node 20。

## 本地安装

在仓库根目录执行。

Windows PowerShell：

```powershell
.\scripts\install.ps1
```

跳过前端依赖：

```powershell
.\scripts\install.ps1 -SkipFrontend
```

Linux/macOS：

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

跳过前端依赖：

```bash
SKIP_FRONTEND=1 ./scripts/install.sh
```

脚本会创建 `backend/.venv`、安装 `backend/requirements.txt`，默认安装前端 npm 依赖，
并仅在文件缺失时把 `backend/.env.example` 复制为 `backend/.env`。示例配置中的 provider
key 是占位值，启动真实模型调用前必须修改。

## 本地开发

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe run.py
```

Linux/macOS 对应命令：

```bash
cd backend
.venv/bin/python run.py
```

前端另开终端：

```bash
cd frontend
npm run dev
```

默认访问：

- Vite 前端：`http://localhost:5173/`
- 后端 OpenAPI UI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/v1/monitor/health`

源码本地运行只有在仓库根的 `frontend_dist/` 已存在时，后端才会挂载 `/ui`。
普通 `npm run build` 产物位于 `frontend/dist/`，不会自动复制到该位置；因此本地开发不能默认假设
`http://localhost:8000/ui/` 可用。

## Docker 镜像与 Compose

从仓库根目录准备本地配置后启动：

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Windows 可使用：

```powershell
Copy-Item backend\.env.example backend\.env
docker compose up --build
```

Compose 包含：

- `backend`：构建 `backend-runtime`，暴露宿主机 `8000`。
- `frontend`：构建 `frontend-runtime`（nginx），暴露宿主机 `5173`。
- `ollama`：只在 `ollama` profile 启用，暴露 `11434` 并使用命名卷 `ollama`。

访问入口：

- 独立 nginx 前端：`http://localhost:5173/`
- 后端 API 文档：`http://localhost:8000/docs`
- 后端镜像内置前端：`http://localhost:8000/ui/`

多阶段 Dockerfile 会先运行 `npm ci` 和 `npm run build`，再把 `frontend/dist` 复制到后端镜像的
`/app/frontend_dist`，因此容器内后端会挂载 `/ui`。该 `/ui` 与独立 frontend 容器是同一份
构建产物的两个服务入口。

backend 镜像内置健康检查：

```text
GET http://127.0.0.1:8000/api/v1/monitor/health
```

间隔 30 秒、超时 5 秒、启动宽限 30 秒、连续 3 次失败判 unhealthy。

## nginx 行为

`deploy/nginx.conf` 用于 `frontend-runtime`：

- `/api/` 代理到 `http://backend:8000/api/`；
- `/docs` 和 `/openapi.json` 代理到后端；
- 其他路径由 nginx 提供前端静态文件，并通过 `try_files` 回退到 SPA `index.html`。

该文件只监听 HTTP 80，没有 TLS、访问认证、限流或安全响应头，也没有把 `/ui/` 显式代理到
backend。经 `http://localhost:5173/ui/` 访问时命中的是前端 SPA fallback，不应与后端
`http://localhost:8000/ui/` 的静态挂载混为一谈。

生产环境应在此配置前后增加受控的 TLS 终止和访问策略，或替换为组织维护的 ingress/API gateway。

## workspace 与持久化

默认 `WORKSPACE_DIR=./workspace`。本地从 `backend/` 启动时对应：

```text
backend/workspace/
```

Compose 将以下宿主目录绑定到 backend 容器：

```text
./backend/workspace   -> /app/workspace
./backend/skills      -> /app/skills
./backend/plugins_ext -> /app/plugins_ext
```

workspace 包含任务队列 SQLite（`tasks/task_queue.sqlite3` + WAL）、旧任务 JSON（`tasks/task_history.json`）、Agent、审批历史、消息历史、访问控制、trace、生成产物，以及默认位于
`workspace/checkpoints/` 的每 Agent 独立 SQLite checkpoint。
必须持久化 `/app/workspace` 才能跨容器重建保留这些数据。技能和插件目录也被绑定挂载，
它们是可执行内容，应限制写权限和变更来源。

默认配置为：

```env
CHECKPOINT_BACKEND=sqlite
CHECKPOINT_SQLITE_PATH=./workspace/checkpoints
```

应用使用 `langgraph-checkpoint-sqlite==3.1.0` 的 `AsyncSqliteSaver`，并为每个 Agent 创建独立数据库。容器/进程或 Agent 实例重建后，
恢复入口会按完整 `ExecutionRef` 解析原 Agent 并核对持久 interrupt；checkpoint 缺失或已完成时返回 409。
`CHECKPOINT_BACKEND=memory` 只用于显式临时降级，`/monitor/health` 会显示
`supports_restart_resume=false`，不得据此宣称跨重启恢复。
当前多数运行数据是 JSON/JSONL 文件，也没有数据库事务或跨进程写锁，部署定位必须保持单实例。SQLite checkpoint 不是多实例共享恢复方案，不能通过简单增加 backend 副本获得一致或高可用的 HITL。

如果把 `WORKSPACE_DIR` 或 `CHECKPOINT_SQLITE_PATH` 改到其他容器路径，必须同步修改 volume 目标；否则应用会把数据写入
未持久化的容器层。备份时应把 workspace 当作敏感数据，并验证恢复，而不是只确认备份文件存在。
备份 SQLite 时应停机或使用 SQLite 一致性备份方式（含任务队列 WAL：备份主库文件并复制 `-wal`/`-shm`，或使用 `backup API`）；升级前先备份全部 checkpoint 与任务队列数据库；官方
`setup()` 只执行向前 schema 初始化，本项目不会在 Agent reload、idle eviction 或删除注册项时隐式清理 checkpoint。

## 可选 Ollama

```bash
docker compose --profile ollama up --build
```

`backend/.env`：

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5
OLLAMA_BASE_URL=http://ollama:11434
```

Ollama 模型数据保存在 Compose 命名卷 `ollama`，首次使用仍需准备相应模型。

## OpenAI-compatible 服务

对于 vLLM、LM Studio、LocalAI 或兼容的 `/v1` 服务：

```env
LLM_PROVIDER=openai
LLM_MODEL=<服务实际提供的模型名>
OPENAI_API_KEY=not-needed
OPENAI_BASE_URL=http://<可从后端访问的主机>:8001/v1
```

容器内的 `localhost` 指 backend 容器自身，不是宿主机。服务在宿主机或其他容器时，应使用该环境
实际可达的 DNS 名称。仅在目标服务确实不鉴权时使用占位 key。

## 生产安全配置

至少审查并显式设置：

```env
CORS_ORIGINS=https://console.example.com
API_TOKEN=<随机长令牌>
API_RATE_LIMIT_PER_MINUTE=<正整数>
CONSOLE_PASSWORD=<强密码，迁移期兼容；团队启用后建议移除>
CONSOLE_JWT_SECRET=<独立随机长密钥>
CONSOLE_JWT_TTL_MINUTES=60
CONSOLE_COOKIE_SECURE=true
BOOTSTRAP_TOKEN=<可选，非本机 bootstrap 时必填>
# IDENTITY_SQLITE_PATH 默认 workspace/identity/identity.sqlite3（需持久化卷）
TOOL_GUARD_ENABLED=true
TOOL_GUARD_LEVEL=smart
CHECKPOINT_BACKEND=sqlite
CHECKPOINT_SQLITE_PATH=/app/workspace/checkpoints
GATEWAY_RATE_LIMIT_PER_MINUTE=<正整数>
ENABLED_PLUGINS=
# 控制台经保险箱保存 Provider API Key 时必需（32 字节随机值，Base64/hex；勿提交真实值）
BOETCLAW_MASTER_KEY=
```

若使用控制台保存 Provider API Key（而非仅依赖 `OPENAI_API_KEY` 等环境变量），必须在部署环境中设置
`BOETCLAW_MASTER_KEY` 并持久化 `workspace/credentials/`。生成方式与威胁边界见 `docs/SECURITY.md`。

还应：

- 只暴露必要端口和路径，对 `/docs`、`/openapi.json`、管理 API、`/ui/` 增加边界访问控制。
- 使用 HTTPS；生产设置 `CONSOLE_COOKIE_SECURE=true`，并持久化 `workspace/identity/`（用户/会话/ACL/审计库）。
- 为启用渠道设置非空用户白名单，并在代理或应用层补齐平台 webhook 签名校验。
- 使用 secrets manager 或受控挂载提供密钥（含 `BOETCLAW_MASTER_KEY` 与 Provider API Key），
  不把真实 `backend/.env` 烘焙进镜像或提交仓库。
- 仅启用审查过的插件/技能；当前插件与后端同进程执行，没有沙箱。
- 以非 root、最小文件系统权限和受限出站网络运行。当前 Dockerfile 没有声明 `USER`，
  默认容器用户不是最小权限配置。
- 对多副本部署使用集中式限流和耐久消息队列；现有限流与渠道队列均为进程内状态。
- 验证默认与 Workspace Agent 的 SQLite interrupt/resume；health 中 checkpoint 状态必须为 `ready`。
- 固定并扫描基础镜像和 Python/npm 依赖；依赖审计已由 CI `security` job（`pip-audit` / `npm audit`）覆盖，镜像 CVE 扫描仍建议在发布流水线另加。

## CI 与 required checks（PLAN-420）

仓库已包含实际 workflow：`.github/workflows/ci.yml`。本地可运行 `scripts/ci-local.ps1` / `scripts/ci-local.sh` 复现主门禁。

**说明**：若工作区尚未 `git init` / 推送到 GitHub，则只有 workflow 文件落盘，云端 Actions 不会自动跑；推送并打开 Actions 后 push/PR 才会触发。

启用 branch protection required checks：

1. 将仓库推送到 GitHub，确认 Actions 已启用，并在默认分支至少成功跑通一次 `CI`。
2. Settings → Branches → Add/Edit branch protection rule（如 `main`）。
3. 勾选 **Require status checks to pass before merging**，搜索并勾选：
   - `Backend (pytest / lint / type / OpenAPI)`
   - `Frontend (test / coverage / build)`
   - `Playwright E2E (chromium / fake Provider)`
   - `Docker Compose config`
   - `Security (pip-audit / npm audit)`
4. `Gitleaks (optional)` 默认 `continue-on-error`，建议先观察再决定是否 required。
5. 真实 Provider/渠道验收仍用发布前手工清单与 `npm run test:e2e:manual`，不要加入默认 required。

## 运维检查

部署后建议逐项验证：

1. `docker compose ps` 中后端健康，frontend 正常运行。
2. `/api/v1/monitor/health` 返回成功；错误的 API token 访问受保护 API 得到 401。
3. 前端根路径、后端 `/ui/`、`/docs` 的暴露范围符合预期。
4. 从 backend 运行环境实际调用 provider，而不是只检查端口。
5. 创建测试任务后重启 backend，任务和 workspace 文件仍存在。
6. 写入渠道白名单后，允许和拒绝用户行为均符合预期。
7. ToolGuard 对敏感路径、写工具和高危 Shell 的阻断/审批符合所选级别。
8. 检查磁盘容量、workspace/checkpoints 增长、容器日志、任务失败、渠道消息失败和 checkpoint health 状态。
9. 执行 workspace 备份恢复演练，并确认权限、加密和保留期。
10. 升级前备份 checkpoint SQLite；合并前依赖 CI / `scripts/ci-local.*`，并另做真实 Provider/渠道手工验收（非默认门禁）。
