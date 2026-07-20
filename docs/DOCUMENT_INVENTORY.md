# BoetClaw 材料台账

> 盘点基准：2026-07-20（首版发布前验证基线同步）  
> 事实优先级：当前源码与可执行配置 > 自动化测试 > 现行文档 > 归档文档。  
> 状态定义：**现行**表示仍作为项目入口或维护文档；**归档**表示仅保留历史语境；**代码事实来源**表示判断当前能力时应直接核对的材料。

## 1. 盘点结论

- 项目现有材料能够覆盖产品介绍、实施过程、架构、API、渠道、安全、部署、运行时技能、配置和自动化测试；“阶段已勾选”仍不等于真实产品闭环。
- `docs/PROGRESS.md` 与 `docs/IMPLEMENTATION_PLAN.md` 是当前落实记录和有效计划；不能单独替代源码、测试与状态报告作为完成度依据。
- `docs/archive/2026-07-15/` 中 5 份 `*_legacy.md` 与同名现行专题内容重复；归档价值是保留 2026-07-15 整理前快照，不应继续双向维护。
- 归档的完整进度与计划保留长篇历史证据，但包含过期判断；当前结论以源码和现行报告为准。
- 后端 pytest **36** 文件 / 全量 **213 passed**（2026-07-20，`backend/.venv/Scripts/python.exe -m pytest -q`）；前端 Vitest **5 files / 29 passed**、Playwright Chromium E2E **8 passed**（fake Provider，2026-07-20）；ruff/mypy/OpenAPI/coverage/build/compose 均通过；`.github/workflows/ci.yml` 与 `scripts/ci-local.*` 已落盘；**Git 已初始化，推送到 GitHub 后启用 Actions / required checks**（目标仓库 `NO1117/boetclaw`）。
- 现行需求、功能、验收、API、架构、计划、进度、测试与导航文档已按 2026-07-20 验证基线复核；PLAN-500/650 文档治理与运维验收同步已完成，后续随代码/契约变更可持续执行。

## 2. 项目文档台账

| 路径 | 用途 | 状态 | 当前边界与处置 |
|---|---|---|---|
| `README.md` | 项目入口、能力边界、快速启动、验证命令和文档索引 | 现行 | 已校正完成度口径；随发布基线维护 |
| `docs/README.md` | 文档导航、阅读顺序、事实优先级和维护规则 | 现行 | 作为文档总入口；新增现行文档时同步登记 |
| `docs/REQUIREMENTS.md` | `REQ-*` 需求、范围、状态和验收原则 | 现行 | 状态以代码闭环为准；部分实现项必须保留具体缺口 |
| `docs/FEATURE_CATALOG.md` | `FUN-*` 功能、实现路径、映射和缺口 | 现行 | 与 REQUIREMENTS、验收清单同步维护 |
| `docs/ACCEPTANCE_CHECKLIST.md` | REQ—FUN—API—PAGE—TEST—PLAN 验收映射 | 现行 | 页面路由与 API 必须按代码/OpenAPI 复核；PLAN-100—700 已映射完成；RBAC/多实例/真实联调等未排期项保持未完成 |
| `docs/PROJECT_STATUS_REPORT.md` | 截至 2026-07-20 的代码事实状态报告 | 现行 | 作为阶段状态入口；外部联通和云端 Actions 不从本地门禁外推 |
| `docs/DOCUMENT_INVENTORY.md` | 全量材料分类、归档与事实来源台账 | 现行 | 作为文档治理入口，随材料增删和基线复核更新 |
| `docs/ARCHITECTURE.md` | 当前系统分层、生命周期、路由、数据流和部署拓扑 | 现行 | 描述当前结构与限制，不混入未实施目标设计 |
| `docs/API.md` | 已重建的 REST API 人工索引 | 现行 | 覆盖当前 Router；字段、校验和状态码仍以运行时 OpenAPI 为契约真源 |
| `docs/SECURITY.md` | ToolGuard、审批、鉴权、限流和扩展安全边界 | 现行 | 应持续揭示 fail-open、恢复关联和单进程安全边界 |
| `docs/CHANNELS.md` | 四渠道、队列、白名单、历史、回发与 stub 边界 | 现行 | 路由验签已有单元测试；真实平台回发须以有凭据联调证明 |
| `docs/DEPLOYMENT.md` | 本地、Compose、nginx、持久化、CI required checks 与生产前置 | 现行 | 定位单机部署；workflow 落盘不等于云端 Actions 已启用 |
| `docs/TESTING.md` | 测试矩阵、命令、最近结果和缺口 | 现行 | 统一最近基线：pytest 213 passed / Vitest 5 files 29 passed / E2E 8 passed；fake 与真实联调分开 |
| `docs/IMPLEMENTATION_PLAN.md` | 当前有效 `PLAN-*` 落地计划 | 现行（计划） | PLAN-100—700 已完成；PLAN-500 可持续再执行；RBAC/多实例/真实联调未排期 |
| `docs/PROGRESS.md` | 当前落实清单和本轮实现记录 | 现行（过程记录） | 勾选须有证据；实现记录含思路/文件/验证 |

## 3. 归档文档台账

| 路径 | 用途 | 状态 | 过期、重复或无效内容 | 最终处置 |
|---|---|---|---|---|
| `docs/archive/2026-07-15/ARCHITECTURE_legacy.md` | 架构专题整理前快照 | 归档 | 与当前 `docs/ARCHITECTURE.md` 内容重复，继续维护无效 | 只读保留；不再更新或引用为当前事实 |
| `docs/archive/2026-07-15/API_legacy.md` | API 索引整理前快照 | 归档 | 归档快照不完整；现行 `docs/API.md` 已重建 | 只读保留；当前契约以现行索引和运行时 OpenAPI 为准 |
| `docs/archive/2026-07-15/CHANNELS_legacy.md` | 渠道说明整理前快照 | 归档 | 与当前 `docs/CHANNELS.md` 重复，缺后续访问控制/限流事实 | 只读保留 |
| `docs/archive/2026-07-15/SECURITY_legacy.md` | 安全说明整理前快照 | 归档 | 与当前 `docs/SECURITY.md` 重复，审批恢复描述过于理想化 | 只读保留 |
| `docs/archive/2026-07-15/DEPLOYMENT_legacy.md` | 部署说明整理前快照 | 归档 | 与当前 `docs/DEPLOYMENT.md` 重复，缺生产限制 | 只读保留 |
| `docs/archive/2026-07-15/IMPLEMENTATION_PLAN_v3_full.md` | 完整 v3 计划历史快照 | 归档 | 含过期审计结论与目标伪代码，不能当作源码事实 | 永久保留为历史；禁止据此直接宣称完成 |
| `docs/archive/2026-07-15/PROGRESS_full.md` | 完整阶段记录历史快照 | 归档 | 早期缺口后来有变化，且完成勾选未覆盖现行状态报告识别的语义问题 | 永久保留为审计轨迹；当前结论以源码和现行报告为准 |

## 4. 运行时技能与 Agent 指令材料

| 路径 | 用途 | 状态 | 主要问题 | 最终处置 |
|---|---|---|---|---|
| `backend/AGENTS.md` | 默认 Agent 长期记忆/领域术语/工作原则 | 代码事实来源 | 写明“复杂任务先规划”，但这是提示约束，不等于所有入口强制进入计划确认 | 保留；与中间件事实分开描述 |
| `backend/skills/drilling-report/SKILL.md` | 钻井日报、周报、完井报告模板与审查要点 | 代码事实来源 | 内容简要，缺版本、依据标准和可验证样例 | 保留并版本化扩充 |
| `backend/skills/chart-visualization/SKILL.md` | 钻井参数与测井图表指导 | 代码事实来源 | 宣称 `well_schematic` 类型，但需由实际工具能力验证；未定义输入 schema | 保留；补工具契约 |
| `backend/skills/code-generation/SKILL.md` | 数据解析、自动化代码生成规范 | 代码事实来源 | 示例依赖 `lasio`，但 `backend/requirements.txt` 未列出 `lasio`；运行环境不保证示例可执行 | 保留；修正文档或补依赖前标为指导性内容 |
| `backend/skills/las-parser/SKILL.md` | LAS 解析与质检流程 | 代码事实来源 | 同样给出 `lasio` 示例，而当前轻量导入实现位于 `backend/app/domain/las_importer.py`，两者实现口径不一致 | 保留；区分“推荐方案”与“当前内置解析器” |
| `backend/skills/hse-compliance/SKILL.md` | HSE 合规检查清单 | 代码事实来源 | 未标注标准来源、地区和版本，不能直接作为法规合规结论 | 保留；输出必须提示人工/法规复核 |
| `backend/plugins_ext/example_echo/manifest.json` | 外部插件示例清单 | 代码事实来源 | 只是示例且默认不启用，不代表插件生态已验证 | 保留为样例 |

## 5. 配置、依赖与部署材料

| 路径 | 用途 | 状态 | 主要问题 | 最终处置 |
|---|---|---|---|---|
| `backend/.env.example` | Provider、鉴权、渠道、工作区、安全、调度、checkpoint、内存、可观测配置样例 | 代码事实来源 | 默认 `OPENAI_API_KEY=sk-your-key-here` 容易被误认成有效配置；checkpoint 默认 SQLite、memory 仅显式降级 | 保留；建议将示例 key 留空 |
| `backend/app/core/config.py` | 环境变量到运行时设置的实际映射 | 代码事实来源 | 文档配置项是否生效应以此文件为准 | 保留 |
| `backend/requirements.txt` | Python 运行与测试依赖 | 代码事实来源 | 多数依赖使用宽松下限，无完整 lock 文件；`langgraph-checkpoint-sqlite==3.1.0` 已单独锁定；缺技能示例所用 `lasio` | 保留；生产前增加完整锁定/依赖审计 |
| `backend/requirements-dev.txt` | 开发/CI 依赖（ruff、mypy、pip-audit 等） | 代码事实来源 | 与 `pyproject.toml` 软门禁配合 | 保留 |
| `backend/pytest.ini` | pytest 路径、async 模式与参数 | 代码事实来源 | 未配置覆盖率门槛、marker 严格检查 | 保留；测试治理阶段可补强 |
| `frontend/package.json` | 前端依赖与 `dev`/`build`/`test`/`test:coverage`/`test:e2e` 脚本 | 代码事实来源 | Vitest/Playwright 仅在 `devDependencies`；真实 Provider 走 `test:e2e:manual` | 保留 |
| `frontend/package-lock.json` | 前端依赖锁 | 代码事实来源 | 可复现构建依据，但不等于依赖安全已审计 | 保留 |
| `frontend/tsconfig.json` | TypeScript 编译约束 | 代码事实来源 | 只覆盖编译，不覆盖行为测试 | 保留 |
| `frontend/vite.config.ts` | Vite、开发代理与 Vitest 配置 | 代码事实来源 | E2E 时 `VITE_E2E_FAKE=1` 关闭 API 代理 | 保留 |
| `frontend/playwright.config.ts` | Playwright 项目、chromium 门禁与 manual 套件 | 代码事实来源 | 默认门禁不含真实 Provider/渠道 | 保留 |
| `Dockerfile` | 前端构建、后端运行、Nginx 前端多阶段镜像 | 代码事实来源 | 使用浮动基础镜像标签/宽松 Python 依赖；没有镜像安全扫描材料 | 保留；生产发布时锁 digest 并扫描 |
| `docker-compose.yml` | backend/frontend/可选 Ollama 编排与卷挂载 | 代码事实来源 | 单实例、本地卷模型；包含卷内 SQLite checkpoint，但不含多实例共享数据库、队列或高可用组件 | 保留；定位开发/单机部署 |
| `deploy/nginx.conf` | 前端静态回退与 API 反代 | 代码事实来源 | 未提供 TLS、安全头、SSE 专门超时/缓冲配置 | 保留；生产由外层网关补齐 |
| `scripts/install.ps1` / `install.sh` | 安装脚本 | 代码事实来源 | 执行 `npm install` 而非 `npm ci` | 保留；开发便利脚本 |
| `scripts/ci-local.ps1` / `ci-local.sh` | 本地复现主 CI 门禁 | 代码事实来源 | 等价于 workflow 主 job，不触发云端 Actions | 保留 |
| `.github/workflows/ci.yml` | push/PR CI workflow | 代码事实来源 | **文件已落盘**；Git 已初始化，推送到 remote 后启用云端 Actions | 保留；启用步骤见 `DEPLOYMENT.md` |
| `backend/openapi.snapshot.json` | OpenAPI 契约快照 | 代码事实来源 | breaking 检查见 `backend/scripts/check_openapi_breaking.py` | 保留 |
| `.gitignore` | 排除虚拟环境、构建产物、`*.tsbuildinfo` 和 `backend/workspace/` | 代码事实来源 | 根目录 `.workspace/` 未在规则中列出 | 保留；若需忽略根运行数据可补规则 |
| `.claude/settings.local.json` | 本地工具/Agent 设置 | 本地配置 | 机器相关，不属于产品能力或交付证明 | 保留本地，不作为项目状态证据 |

## 6. 测试材料台账

### 6.1 后端测试文件

以下均为**代码事实来源**。2026-07-20 最近执行 `backend/.venv/Scripts/python.exe -m pytest -q`，全量 **213 passed**。这些测试大量使用 fake、monkeypatch、临时 JSON 和 TestClient；PLAN-110/120/130 专项使用真实 SQLite saver 与最小 LangGraph 图，PLAN-130/200 覆盖 ASGI API，PLAN-210 覆盖单进程任务与运行取消，PLAN-300 覆盖领域 CRUD，PLAN-600—710 覆盖 Cron history、Heartbeat、渠道路由验签、插件扫描删除、Agent 磁盘/purge、会话归档等运维闭环。整体结果证明单实例回归契约，不等于真实 Provider、真实渠道、多实例、跨资源 exactly-once、跨进程取消或生产环境端到端验收。

| 路径 | 主要覆盖 | 问题与最终处置 |
|---|---|---|
| `backend/tests/test_smoke.py` | 应用导入与基础冒烟 | 保留 |
| `backend/tests/test_phase1_core.py` | 工厂、中间件、启动核心 | 保留 |
| `backend/tests/test_phase2_plan.py` | PlanGate、fake graph interrupt/resume、编辑与失败审计 | 保留 |
| `backend/tests/test_phase3_security.py` | Guardian、ToolGuard、审批持久化/i18n | 保留；真实审批中断到恢复由 PLAN-120 专项覆盖 |
| `backend/tests/test_phase4_skills.py` | 技能解析、扫描、安装/工作区 | 保留 |
| `backend/tests/test_phase5_agents.py` | 多 Agent 路由、隔离、并发懒加载 | 保留 |
| `backend/tests/test_phase6_providers.py` | Provider、base URL、配置与限流 | 保留；外部连通性仍需独立集成测试 |
| `backend/tests/test_phase7_memory.py` | 来源策略、摘要与 memory backend | 保留；checkpoint 跨重启由 PLAN-110 专项覆盖 |
| `backend/tests/test_phase8_channels.py` | 四渠道解析、队列与消费者 | 保留；真实平台凭据回发需验收 |
| `backend/tests/test_phase9_scheduler.py` | Cron、心跳与自动化来源 | 保留 |
| `backend/tests/test_phase10_plugins.py` | 插件、命令、语言覆盖 | 保留；真实 `/stop` 取消由 `test_plan210_cancellation.py` 覆盖 |
| `backend/tests/test_phase12_observability.py` | Trace、timeline、OTel、metrics | 保留 |
| `backend/tests/test_phase14_sessions.py` | 会话 JSON 持久化 | 保留 |
| `backend/tests/test_phase15_mcp.py` | MCP 状态、工具、reload 指标 | 保留；真实服务器恢复需集成测试 |
| `backend/tests/test_phase15_gateway_ops.py` | 渠道运维状态/历史/重试 | 保留 |
| `backend/tests/test_phase16_domain.py` | DomainStore CRUD 与领域创建/查询路由 | 保留；完整关联 CRUD 见 PLAN-300 专项 |
| `backend/tests/test_phase16_domain_tools.py` | 领域数据工具适配 | 保留 |
| `backend/tests/test_phase16_las_import.py` | LAS 解析、上传、质检与上传门禁 | 保留 |
| `backend/tests/test_phase16_artifacts.py` | 产物列表、预览/下载、删除与 metadata 清理 | 保留 |
| `backend/tests/test_phase17_agent_index.py` | Agent 文件与历史索引 | 保留 |
| `backend/tests/test_phase17_artifact_meta.py` | 产物侧车元数据 | 保留 |
| `backend/tests/test_phase23_api_security.py` | Token/JWT、限流、健康豁免 | 保留 |
| `backend/tests/test_phase24_task_persistence.py` | 任务 JSON 落盘与重启恢复 | 保留 |
| `backend/tests/test_phase25_gateway_access_control.py` | 渠道白名单、拒绝与持久化 | 保留 |
| `backend/tests/test_plan100_execution_ref.py` | ExecutionRef、恢复校验、审批顺序和 fail-closed | 保留 |
| `backend/tests/test_plan110_checkpoint.py` | SQLite provider/Agent 重建恢复、Agent DB 隔离、memory 降级和 interrupt 校验 | 保留；不外推为多实例共享恢复 |
| `backend/tests/test_plan120_tool_approval.py` | 真实 LangGraph 工具审批、幂等/并发裁决、SQLite 重建和非默认 resolver | 保留；不外推为跨资源或分布式 exactly-once |
| `backend/tests/test_plan130_multi_agent_plan.py` | 真实最小 LangGraph + SQLite/API 的多 Agent 计划确认、隔离与重建恢复 | 保留 |
| `backend/tests/test_plan200_stream_chat.py` | ASGI/fake Agent 的同步/SSE 编排、Workspace 路由、事件 envelope 与 done/error 语义 | 保留 |
| `backend/tests/test_plan210_cancellation.py` | 长运行 fake Agent 的底层取消、状态竞态、Agent/thread 隔离、`/stop`、run API 与 shutdown | 保留；不外推为跨进程取消 |
| `backend/tests/test_plan300_domain_crud.py` | 关联实体 CRUD/404/409、LAS 文件策略、旧 JSON、备份/原子写和并发 | 保留；不外推为数据库事务 |
| `backend/tests/test_plan600_cron_history.py` | Cron 运行历史落盘、重启加载、上限截断 | 保留 |
| `backend/tests/test_plan610_heartbeat_persist.py` | Heartbeat `.env` 落盘与热重调度 | 保留 |
| `backend/tests/test_plan620_webhook_signature.py` | 四渠道路由验签、skipped/verified、中间件豁免 | 保留；不外推为真实平台联调 |
| `backend/tests/test_plan630_plugin_scan_delete.py` | 插件安装扫描门禁、scan-report、DELETE 清理 | 保留；静态扫描非沙箱 |
| `backend/tests/test_plan640_agent_disk_purge.py` | Agent 磁盘发现、tombstone、purge、resume 409 | 保留 |

### 6.2 前端与 CI 材料

| 路径 | 用途 | 状态 | 问题 | 最终处置 |
|---|---|---|---|---|
| `frontend/src/` | React 页面与组件源码 | 代码事实来源 | 路由手写、页面逻辑集中；非关键页组件覆盖仍薄 | 保留 |
| `frontend/src/**/*.test.ts(x)` | Vitest 组件/协议测试（5 文件 / 25 项） | 代码事实来源 | 覆盖 SSE/chatStream/计划/审批/停止/领域请求；不含全页面 | 保留；PLAN-400 |
| `frontend/e2e/` | Playwright 规格与 fake backend fixture | 代码事实来源 | 默认 chromium 8 项（fake）；`manual/` 真实 Provider 不进 PR 门禁 | 保留；PLAN-410 |
| `frontend/package.json` 的 `build` | `tsc -b && vite build` | 代码事实来源 | 本轮构建通过 | 保留为最低门槛 |
| `.github/workflows/ci.yml` | 实际 CI workflow | 代码事实来源 | workflow 已落盘；云端 Actions / required checks 待远程启用 | 保留；不得宣称云端已跑通 |
| `scripts/ci-local.*` | 本地等价门禁 | 代码事实来源 | 本机 2026-07-17 复验通过 | 保留 |
| `frontend/dist/` | 前端构建输出 | 构建产物 | 可由源码重建，不是事实文档 | 保留，不手工维护 |

## 7. 代码事实来源索引

| 事实主题 | 应核对路径 |
|---|---|
| 应用路由与生命周期 | `backend/app/main.py`、`backend/app/api/routes/` |
| 默认 Agent、同步调用、流式与计划恢复 | `backend/app/core/agent.py`、`backend/app/api/routes/agent.py` |
| 多 Agent 构建与 checkpoint | `backend/app/agents/multi_agent_manager.py`、`backend/app/agents/runtime.py`、`backend/app/core/checkpoint.py` |
| PlanGate 与 ToolGuard | `backend/app/middleware/plan_gate_mw.py`、`backend/app/middleware/tool_guard_mw.py` |
| 审批记录与恢复 API | `backend/app/security/approval.py`、`backend/app/api/routes/security.py` |
| 任务执行和取消 | `backend/app/api/routes/tasks.py`、`backend/app/services/run_registry.py`、`backend/app/services/task_scheduler.py` |
| 领域数据与 LAS | `backend/app/api/routes/domain.py`、`backend/app/domain/`、`backend/app/tools/builtin.py` |
| 前端路由、页面和领域 UI | `frontend/src/App.tsx`、`frontend/src/services/api.ts` |
| 前端同步/流式/计划/审批交互 | `frontend/src/components/ChatPanel.tsx`、`PlanConfirm.tsx`、`ApprovalCard.tsx` |
| 前端自动化测试 | `frontend/src/**/*.test.*`、`frontend/e2e/`、`frontend/playwright.config.ts` |
| CI / OpenAPI | `.github/workflows/ci.yml`、`backend/openapi.snapshot.json`、`scripts/ci-local.*` |
| 部署与反代 | `Dockerfile`、`docker-compose.yml`、`deploy/nginx.conf` |

## 8. 本轮处置边界

1. 复核并纠偏现行文档，不修改 `docs/archive/` 中任何历史快照。
2. 不修改业务代码、运行时数据、环境或构建产物。
3. 当前事实仍按“源码与可执行配置 > 自动化测试与可重复验证 > 现行文档 > 归档文档”判断。
4. 计划、进度和归档中的历史日期与事件语境保留；“当时基线”与“最近验证基线”分开书写，避免用旧数字覆盖现行结论。
5. PLAN-500 本轮已完成闭环治理记录；后续代码/契约变更时应再跑同一检查清单。
