# 测试说明

> 文档基线：2026-07-28。

## 当前基线

事实来源为 `backend/tests/`、`backend/pytest.ini`、`frontend/package.json` 和本次本地执行结果（2026-07-20）。

- 后端共有 36 个 `test_*.py` 文件。
- `.\.venv\Scripts\python.exe -m pytest --collect-only` 实际收集 213 个用例。
- PLAN-710 专项：`tests/test_phase14_sessions.py` 4 passed；全量基线按 collect-only `213`。
- PLAN-210 状态为已完成：任务、同步/SSE、渠道 Agent 子任务、`/stop` 和运行取消 API 已纳入单进程执行级取消；边界是不支持跨进程、多副本或服务重启后的活动运行取消。
- 前端已配置 Vitest/jsdom/Testing Library、V8 覆盖率报告和关键协议模块门槛。
- 前端现有 5 个测试文件、29 项组件/协议测试（含会话归档契约）。
- 浏览器 E2E（PLAN-410）已建立并复验：默认 Chromium + fake Provider 门禁（2026-07-20 `npm run test:e2e` 8 passed）；真实 Provider/渠道为 optional manual 套件。项目级 CI（PLAN-420）已落地：`.github/workflows/ci.yml` + `scripts/ci-local.*`；**Git 已初始化，推送到 GitHub 后启用 Actions / required checks**。Vitest 排除 `e2e/**`，`npm test` 仅跑组件/协议单测。

以上数字是当前快照，不应理解为长期固定指标。

## 测试策略

当前测试以快速、隔离的后端测试为主：

1. 单元测试覆盖安全 guardian、限流器、存储、解析器、渲染器等纯逻辑。
2. 路由测试通过 FastAPI 测试客户端和 monkeypatch 验证主要 API 行为。
3. 异步测试由 `pytest-asyncio` 自动模式执行，配置见 `backend/pytest.ini`。
4. 文件持久化测试主要使用 pytest `tmp_path`，避免污染真实 workspace。
5. 外部 LLM、消息平台、MCP 和可观测性服务大多被替身或 monkeypatch 隔离；测试通过不等同于第三方真实联调通过。

## 后端覆盖矩阵

“用例数”按源码测试函数定义计数；参数化后 pytest 实际收集数为 **213**（2026-07-17 `--collect-only` 汇总）。

| 测试文件 | 用例数 | 当前覆盖重点 |
| --- | ---: | --- |
| `test_smoke.py` | 3 | 应用导入、配置字段、事件类型 |
| `test_phase1_core.py` | 3 | 可观测中间件、Agent factory、启动函数 |
| `test_phase2_plan.py` | 7 | Plan Gate、计划中断/确认/编辑、计划历史 |
| `test_phase3_security.py` | 14 | ToolGuard guardian、策略级别、中间件、审批持久化 |
| `test_phase4_skills.py` | 7 | skill frontmatter、静态扫描、技能池和治理路由 |
| `test_phase5_agents.py` | 4 | 路由优先级、多 Agent 隔离、并发懒加载 |
| `test_phase6_providers.py` | 13 | provider 管理、模型配置、能力缓存、provider 限流、配置路由不写明文 `.env` |
| `test_provider_credential_vault.py` | 14 | 保险箱加解密/篡改/轮换、无主密钥降级、连接 CRUD/409、env 导入不删 `.env`、日志脱敏、validate-only |
| `test_phase7_memory.py` | 7 | 记忆来源策略、存储后端、上下文摘要 |
| `test_phase8_channels.py` | 9 | 四渠道解析、渲染、队列满和消费者 |
| `test_phase9_scheduler.py` | 7 | cron/heartbeat、来源隔离、失败历史 |
| `test_plan600_cron_history.py` | 3 | Cron 运行历史落盘、重启加载、上限截断 |
| `test_plan610_heartbeat_persist.py` | 3 | Heartbeat `.env` 落盘、启停重调度、路由委托 |
| `test_phase10_plugins.py` | 14 | 插件启用边界、命令/i18n、插件治理路由 |
| `test_plan620_webhook_signature.py` | 11 | 四渠道路由验签、`skipped`/`verified`、中间件豁免 |
| `test_plan630_plugin_scan_delete.py` | 6 | 安装扫描门禁、scan-report、DELETE 清理、路径穿越 |
| `test_attachment_production.py` | 8 | 两阶段上传、Agent 隔离、解析/重试/删除、attachment_ids 聊天、会话引用清理 |
| `test_chat_attachments.py` | 11 | 内联 Base64 兼容、vision 校验、模型 override |
| `test_phase12_observability.py` | 6 | trace、timeline、OTel、Prometheus 文本 |
| `test_phase14_sessions.py` | 4 | 会话记录、列表、导出、删除、归档过滤与 API |
| `test_phase15_gateway_ops.py` | 3 | 渠道状态、消息历史/重试、网关限流 |
| `test_phase15_mcp.py` | 2 | MCP 管理与重载计数 |
| `test_phase16_artifacts.py` | 3 | 产物列表/下载、SHA256、路径逃逸拒绝、产物删除与 metadata 清理 |
| `test_phase16_domain.py` | 3 | 领域存储 CRUD、关联对象约束 |
| `test_phase16_domain_tools.py` | 2 | 钻井参数查询和 mock 回退 |
| `test_phase16_las_import.py` | 4 | LAS 解析、导入、上传持久化、上传扩展名/大小/内容门禁 |
| `test_phase17_agent_index.py` | 1 | Agent 文件索引和历史 |
| `test_phase17_artifact_meta.py` | 1 | 生成代码 sidecar 元数据 |
| `test_phase23_api_security.py` | 5 | API Token、健康检查豁免、API 限流、Console JWT |
| `test_phase24_task_persistence.py` | 2 | 任务 SQLite 持久化、重启后 running → interrupted |
| `test_durable_task_queue.py` | 11 | 迁移幂等、租约、并发、重试分类、dead-letter、分页、脱敏、竞态 |
| `test_phase25_gateway_access_control.py` | 4 | 渠道白名单持久化、允许/拒绝、用户限流 |
| `test_plan100_execution_ref.py` | 10 | ExecutionRef、Interrupt 解析、错误 ref、审批顺序、适配器校验失败审计、旧 JSON、fail-closed、恢复语义隔离 |
| `test_plan110_checkpoint.py` | 11 | SQLite provider/Agent 重建恢复、每 Agent DB 隔离、memory 降级、生命周期、interrupt 校验与审批重启策略 |
| `test_plan120_tool_approval.py` | 7（参数化后 8） | 真实 LangGraph 工具审批、批准/拒绝执行次数、节点重放幂等、并发裁决、失败终态、SQLite/adapter 重建与非默认 Agent resolver |
| `test_plan130_multi_agent_plan.py` | 2 | 真实最小 LangGraph + SQLite/API；同 thread 双 Workspace approve/edit/reject、history 联合筛选、跨 Agent 伪造 ref、reload/evict/restart、删除/未知 Agent、default 兼容与旧 JSON |
| `test_plan200_stream_chat.py` | 5（参数化后 6） | ASGI/fake Agent；default/nondefault、共享 resolver、`/plan` interrupt、slash command、lang/source、session、error、done once 和 v1 envelope |
| `test_plan210_cancellation.py` | 7 | 长运行 fake Agent、底层 CancelledError、终态保护、Agent/thread 隔离、重复取消、竞态、`/stop`、运行取消 API、interrupt 与清理 |
| `test_plan300_domain_crud.py` | 10 | 关联实体 CRUD/404、井依赖 409、LAS 安全删除、旧 JSON、备份/原子写和进程内并发 |

## 测试命令

先从仓库根目录安装依赖：

```powershell
.\scripts\install.ps1
```

Windows PowerShell：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests\test_phase3_security.py
.\.venv\Scripts\python.exe -m pytest tests\test_provider_credential_vault.py
.\.venv\Scripts\python.exe -m pytest tests\test_phase6_providers.py -k "persist_api_key or config_routes"
.\.venv\Scripts\python.exe -m pytest -k "gateway"
.\.venv\Scripts\python.exe -m pytest --collect-only
```

Linux/macOS：

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_phase3_security.py
.venv/bin/python -m pytest tests/test_provider_credential_vault.py
.venv/bin/python -m pytest tests/test_phase6_providers.py -k "persist_api_key or config_routes"
.venv/bin/python -m pytest -k gateway
.venv/bin/python -m pytest --collect-only
```

Provider 凭据保险箱与连接管理（专项，需 `conftest.py` 注入临时 `BOETCLAW_MASTER_KEY`）：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_provider_credential_vault.py -v
.\.venv\Scripts\python.exe -m pytest tests\test_phase6_providers.py::test_provider_config_routes_do_not_persist_api_key_to_env -v
```

```bash
cd backend
.venv/bin/python -m pytest tests/test_provider_credential_vault.py -v
.venv/bin/python -m pytest tests/test_phase6_providers.py::test_provider_config_routes_do_not_persist_api_key_to_env -v
```

**覆盖要点**（`test_provider_credential_vault.py`）：

- 加解密往返、密文篡改检测、主密钥轮换后仍可解密
- 未配置主密钥时 vault 写入禁用（503），环境变量 Provider 仍 `is_configured`
- 连接创建/列表不泄漏 `api_key`；revision 冲突与默认连接引用删除保护（409）
- `import-env` 不修改 `.env` 且 `env_cleanup_required`
- Provider 配置 PUT 不写明文到 `.env`；`validate_only` 不落盘
- `redact_text` / `emit_event` 不包含完整密钥

前端 Provider 连接（Vitest，`ProviderSettings.test.tsx`）：

```bash
cd frontend
npm test -- --run ProviderSettings
```

- 列表/编辑不回填 API Key；创建后清空密钥字段
- 保险箱未配置提示；导入 env 响应；连接检测与保存错误展示

前端测试与生产构建：

```bash
cd frontend
npm test -- --run
npm run test:coverage
npm run build
```

浏览器 E2E（Playwright / Chromium，默认 fake Provider 门禁）：

```bash
cd frontend
# 首次或升级后安装浏览器二进制（仅 Chromium 即可跑默认门禁）
npx playwright install chromium
# 如需系统依赖（Linux CI 常见）：
# npx playwright install --with-deps chromium

npm run test:e2e
```

可选真实 Provider/渠道联调（不进默认 PR 门禁）：

```bash
# 需已启动真实后端，并设置：
#   E2E_REAL_BASE_URL=http://127.0.0.1:5173
#   E2E_CONSOLE_PASSWORD=...   # 若启用 CONSOLE_PASSWORD
#   E2E_REAL_PROVIDER=1        # 才跑真实 LLM 对话用例
npm run test:e2e:manual
```

可选隔离 ASGI fake Agent 后端（非默认门禁依赖）：

```powershell
cd backend
$env:E2E_WORKSPACE_DIR="D:\tmp\boetclaw-e2e-ws"
.\.venv\Scripts\python.exe scripts\e2e_fake_server.py
```

失败时产物位于 `frontend/test-results/`（trace / screenshot / video）与 `frontend/playwright-report/`；失败用例还会附加 browser console 与 fake-backend 快照。

测试依赖由 npm 实际解析并写入 `devDependencies`：Vitest `4.1.10`、jsdom `29.1.1`、Testing Library React `16.3.2`、jest-dom `6.9.1`、user-event `14.6.1`、coverage-v8 `4.1.10`、`@playwright/test` `1.61.1`。测试依赖不属于生产 dependencies，Vite 生产构建不会打入测试代码。

前端 25 项用例覆盖：

- `sse.test.ts`：多行 data、CRLF/CR、网络分块、末块 flush、注释/空块和无效 JSON。
- `api.test.ts`：v1/legacy envelope、done once、error/提前断流、HTTP/网络/鉴权错误、abort 后服务端取消、取消失败降级、计划/审批完整 ExecutionRef、领域更新/删除请求。
- `PlanConfirm.test.tsx`：服务端原始引用传递、成功回调和失败可见。
- `ApprovalCard.test.tsx`：pending/resuming/不可恢复、恢复失败和重复点击防护。
- `ChatPanel.test.tsx`：停止动作调用流控制并展示服务端取消确认。

覆盖率只对独立关键协议模块设门槛，避免为聚合 service 刷低价值用例。`sse.ts` 门槛为 statements/lines 95%、branches 85%、functions 100%；`chatStream.ts` 为 statements/lines 75%、branches 65%、functions 80%。本次实测两模块合计 statements 97.19%、branches 82.05%、functions/lines 100%。Vitest 排除 `frontend/e2e/**`，`npm test` 不加载 Playwright 规格。

## CI 门禁（PLAN-420）

GitHub Actions 真源：`.github/workflows/ci.yml`（push/PR）。干净 `ubuntu-latest`，缓存 pip/npm，不缓存业务 workspace。

| Job | 命令要点 | 备注 |
|---|---|---|
| backend | `ruff check`、`mypy app`、`scripts/check_openapi_breaking.py`、`pytest` | OpenAPI 快照见 `backend/openapi.snapshot.json` |
| frontend | `npm test -- --run`、`npm run test:coverage`、`npm run build` | 覆盖率门槛见上 |
| e2e | `npx playwright install --with-deps chromium` + `npm run test:e2e` | 不含 `test:e2e:manual` |
| compose | `docker compose config --quiet` | 仅校验语法 |
| security | `pip-audit -r requirements.txt`、`npm audit --omit=dev --audit-level=high` | 阻断 high+；gitleaks 可选非阻断 |
| gitleaks | `gitleaks/gitleaks-action` | `continue-on-error: true` |

本地复现（等价主门禁）：

```powershell
.\scripts\ci-local.ps1
# 或跳过较慢项：
.\scripts\ci-local.ps1 -SkipE2E -SkipSecurity
```

```bash
chmod +x scripts/ci-local.sh
./scripts/ci-local.sh
# ./scripts/ci-local.sh --skip-e2e --skip-security
```

更新 OpenAPI 快照（故意破坏性变更后）：

```bash
cd backend
PYTHONPATH=. python scripts/export_openapi.py
# 将 backend/openapi.snapshot.json 随 PR 提交
```

失败产物：前端 `coverage/`、`test-results/`、`playwright-report/`；CI 通过 `actions/upload-artifact` 上传。

本机 2026-07-20 等价验证：ruff/mypy/OpenAPI/pytest `213 passed`、Vitest `5 files / 29 passed`、`npm run test:coverage`/`npm run build`/`docker compose config --quiet` 通过；Playwright E2E `8 passed`（fake Provider）；CI workflow 已落盘。PLAN-600—710 运维闭环已完成。

## 现有缺口

- 默认 E2E 使用 Playwright route fake Provider/后端，不证明真实 LLM 或渠道联通；真实联调见 `npm run test:e2e:manual`。
- 云端 GitHub Actions / branch protection required checks 需在仓库推送并启用 Actions 后配置（步骤见 `DEPLOYMENT.md`）；镜像 CVE 扫描尚未做阻断门禁。
- 前端覆盖率门槛当前只约束 SSE/流式协议模块，不代表全部页面已有高覆盖率。
- 四个消息渠道已有路由验签单元测试；仍缺少真实平台回调与回发联调。
- API 安全测试未覆盖反向代理、HTTPS、跨进程/多实例限流和密钥轮换。
- PLAN-100 已覆盖 ToolGuard 中断异常 fail-closed；规则/正则仍缺更广泛的绕过、编码混淆和路径规范化对抗用例。
- PLAN-120 已用真实最小 LangGraph 图覆盖正常流程中 approve handler 一次、reject 零次、重放/重复/并发裁决不重复及 SQLite 重建恢复；这不证明工具外部副作用与本地状态之间具备跨资源或分布式 exactly-once。
- PLAN-130 已用真实最小 LangGraph、每 Agent SQLite 和 ASGI API 覆盖多 Agent 计划恢复及生命周期重建；不覆盖真实 LLM 生成计划、浏览器 E2E、多实例共享恢复或流式路径。
- PLAN-210 已以长运行 fake Agent 覆盖任务、同步/SSE、`/stop`、运行取消 API、状态竞态与 shutdown 清理；不覆盖跨进程、多副本或服务重启后的活动运行取消。
- 插件动态导入未在 OS/容器沙箱中测试。
- 消息历史重启后不保留 `_message` 对象，因此持久化记录的重试能力未覆盖为可用能力。
- 外部 provider、MCP、OTel exporter 的故障注入和长时间稳定性测试有限。
- 保险箱默认 E2E 使用 fake backend 路由，不验证真实 AES 磁盘文件；真实主密钥 + vault 文件权限需在部署验收中手工确认。

## 建议验收用例

发布前至少手工或自动完成以下高风险路径：

1. 未配置鉴权时仅允许在可信本地环境使用；配置 `API_TOKEN` 后验证无 token 为 401，Bearer 和 `X-API-Token` 可用。
2. 配置 Console 密码和独立 `CONSOLE_JWT_SECRET`，验证登录、过期、篡改 token、退出和 Cookie 行为。
3. 分别在 `strict`、`smart`、`auto` 下验证读工具、写文件、Shell 高危命令、敏感路径和拒绝审批。
4. 执行 `/plan` 流程，确认规划阶段无法调用普通工具，确认/编辑/拒绝后状态和历史符合预期。
5. 为四渠道设置非空白名单，验证未列入用户不会创建 Agent 任务；再验证按渠道+用户的分钟限流。
6. 在测试账号上完成四渠道 webhook 到真实回发的闭环，并验证平台侧鉴权；路由已调用 `verify_signature()`（单元测试覆盖），真实联调仍须配置非空平台密钥与凭据。
7. 填满渠道队列，确认 fallback 的任务创建、消息历史状态和告警符合运维预期。
8. 重启服务，验证任务、审批、访问控制、消息历史和 Agent workspace 的恢复；同时确认旧消息记录不能直接重试的限制。
9. 安装含测试密钥和危险调用的技能/插件，确认扫描报告与安装拒绝；验证未列入 `ENABLED_PLUGINS` 时不会导入，DELETE 后目录与启用列表一致。
10. 使用 Docker Compose 启动，检查后端健康、独立前端、`/ui/`、反向代理 API 及 workspace 重启持久化。
