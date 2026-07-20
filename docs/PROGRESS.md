# BoetClaw 落实清单与实现记录

> 更新日期：2026-07-17。本文记录当前有效落实项与本轮文档系统化过程。  
> 图例：`[x]` 已完成并有证据；`[~]` 已有主体但未闭环；`[ ]` 尚未实现。  
> 原始 Phase 0—46 长记录已归档至 `archive/2026-07-15/PROGRESS_full.md`，不再与现行文件双向维护。

## 一、可视化落实清单

### 本轮文档系统化

- [x] DOC-017 代码—文档一致性复核与纠偏
- [x] DOC-018 测试、构建及 Compose 复验
- [x] DOC-001 建立 `DOCUMENT_INVENTORY.md` 材料台账
- [x] DOC-002 建立 `PROJECT_STATUS_REPORT.md` 代码事实状态报告
- [x] DOC-003 重写 `REQUIREMENTS.md`，建立 REQ 编号体系
- [x] DOC-004 重写 `FEATURE_CATALOG.md`，建立 FUN 编号及 REQ 映射
- [x] DOC-005 归档原始专题、完整计划和完整进度到 `archive/2026-07-15/`
- [x] DOC-006 重写 `ARCHITECTURE.md`
- [x] DOC-007 重写 `API.md`，明确 OpenAPI 为契约真源
- [x] DOC-008 重写 `TESTING.md`
- [x] DOC-009 重写 `SECURITY.md`
- [x] DOC-010 重写 `CHANNELS.md`
- [x] DOC-011 重写 `DEPLOYMENT.md`
- [x] DOC-012 重写 `docs/README.md` 文档导航与治理规则
- [x] DOC-013 重写 `IMPLEMENTATION_PLAN.md` 为当前项目落地计划书
- [x] DOC-014 重写 `PROGRESS.md` 为落实清单与实现记录
- [x] DOC-015 新建 `ACCEPTANCE_CHECKLIST.md` 验收映射
- [x] DOC-016 更新根 `README.md` 文档索引与项目状态摘要

### 已验证代码基线

- [x] 后端 pytest：2026-07-17 项目虚拟环境全量收集 `213` 项
- [x] 前端 TypeScript/Vite 生产构建通过
- [x] 前端 Vitest：26 项；Playwright Chromium E2E：8 项（fake Provider）
- [x] `docker compose config --quiet` 通过
- [~] 默认 Agent 同步聊天、计划确认、会话和 Trace 主路径存在
- [x] ToolGuard 风险检测、幂等审批、真实 interrupt/resume 与审计闭环
- [x] 多 Agent 工作区、文件隔离、磁盘列表发现与删除/purge
- [x] 默认/Workspace Agent SSE 与同步请求语义统一
- [x] 任务创建、重跑、状态持久化与执行级取消闭环
- [x] 井、井段、日报、参数、LAS 的领域 CRUD、关系保护和关联导航闭环

### 真实未闭环开发项

- [x] PLAN-100 统一审批/计划可恢复运行标识，拆分恢复语义
- [x] PLAN-110 将 `MemorySaver` 替换为持久化 checkpoint
- [x] PLAN-120 完成工具审批真实执行、单次执行与幂等裁决
- [x] PLAN-130 完成多 Agent 计划 API 往返与隔离验收
- [x] PLAN-200 统一同步与流式的 Agent、命令、语言、source 和会话语义
- [x] PLAN-210 实现任务、`/stop` 与流式运行的真正取消
- [x] PLAN-300 补齐日报、参数、LAS CRUD、关系约束和页面导航
- [x] PLAN-400 建立前端组件/协议测试
- [x] PLAN-410 建立 Playwright E2E
- [x] PLAN-420 建立实际 CI 与契约门禁
- [x] PLAN-500 文档持续治理（本轮闭环已完成；可持续再执行）

### 阶段 F：运维闭环（PLAN-600+）

- [x] PLAN-600 Cron 运行历史持久化
- [x] PLAN-610 Heartbeat 配置持久化与热更新
- [x] PLAN-620 渠道 webhook 验签接入
- [x] PLAN-630 插件扫描与删除治理
- [x] PLAN-640 Agent 磁盘发现与删除清理
- [x] PLAN-650 运维阶段文档与验收同步
- [x] PLAN-660 Agent 空闲逐出生命周期调度
- [x] PLAN-670 会话历史删除闭环
- [x] PLAN-680 产物删除闭环
- [x] PLAN-690 产物 SHA256 校验和
- [x] PLAN-700 LAS 上传基础门禁
- [x] PLAN-710 会话归档闭环

### PLAN-710 会话归档闭环

- **实现思路**：`FUN-006` 已支持会话列表、搜索、恢复、导出和删除，但缺少归档能力，活跃侧栏会与过期会话混杂。按最小闭环在会话 JSON 上增加 `archived`/`archived_at`，默认列表隐藏已归档；提供归档/取消归档 API 与前端「仅显示已归档」切换。归档不等于删除，不清理 Trace、checkpoint 或其他运行数据。
- **修改文件**：`backend/app/memory/session_store.py`、`backend/app/api/routes/agent.py`、`backend/tests/test_phase14_sessions.py`、`backend/openapi.snapshot.json`、`frontend/src/services/api.ts`、`frontend/src/services/api.test.ts`、`frontend/src/App.tsx`、`frontend/src/App.css`；同步 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/FEATURE_CATALOG.md`、`docs/API.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/TESTING.md`、`docs/REQUIREMENTS.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/DOCUMENT_INVENTORY.md`、`docs/README.md`、根 `README.md`。
- **核心代码变更**：
  - `SessionStore.archive_session` / `unarchive_session`：写入或清除归档标记与时间戳。
  - `list_sessions(..., include_archived=, archived_only=)`：默认隐藏已归档；支持全量或仅归档视图。
  - `POST /api/v1/agent/sessions/{thread_id}/archive|unarchive`：返回 `{thread_id, archived, archived_at}`；不存在 404。
  - `GET /sessions` 增加 query `include_archived`、`archived_only`。
  - 前端 `archiveChatSession` / `unarchiveChatSession`；ChatHistoryPanel 增加归档按钮与「仅显示已归档」开关。
- **遇到的问题与解决方案**：若默认列表同时混入已归档，会削弱归档的清理语义。解决方式是默认隐藏，并用独立 `archived_only` 视图查看，而不是仅靠前端过滤。
- **验证状态（2026-07-17）**：`backend/.venv/Scripts/python.exe -m pytest -q tests/test_phase14_sessions.py` → 4 passed；`--collect-only` 汇总 `213`；`npm test -- --run src/services/api.test.ts` → 18 passed；OpenAPI export + breaking check OK（123 operations）。
- **遗留边界**：仍无分页游标与并发控制；归档状态随会话 JSON 持久化，不引入独立归档库或保留策略。

### PLAN-700 LAS 上传基础门禁

- **实现思路**：`FUN-105` 已支持 LAS 路径导入和上传解析，但上传路径没有明确的扩展名、大小和内容级拒绝，明显非 LAS 文件也会先写入再进入解析。本项在上传写盘前增加基础门禁：仅允许 `.las`，默认最大 `10MB`，内容必须包含 LAS 曲线段与数据段标记；拒绝时不创建上传文件、不创建 LAS 记录。
- **修改文件**：`backend/app/core/config.py`、`backend/.env.example`、`backend/app/api/routes/domain.py`、`backend/tests/test_phase16_las_import.py`；同步 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/FEATURE_CATALOG.md`、`docs/API.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/TESTING.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/DOCUMENT_INVENTORY.md`、`docs/README.md`、根 `README.md`。
- **核心代码变更**：
  - `Settings.las_upload_max_bytes`：新增 `LAS_UPLOAD_MAX_BYTES`，默认 `10485760`。
  - `_validate_las_upload(name, content)`：校验 `.las` 扩展名、大小上限和 `~A` + `~C/~Curve` 段标记。
  - `upload_las()`：读取内容后先校验，通过后才创建 `las_uploads` 目录和写文件。
  - `test_las_upload_rejects_extension_size_and_content`：覆盖扩展名、大小和内容三类失败均不落盘、不落库。
- **遇到的问题与解决方案**：若先创建上传目录再校验，会留下空目录，削弱“拒绝不落盘”的语义。解决方式是把目录创建和文件命名冲突处理移动到校验通过之后。
- **验证状态（2026-07-17）**：`backend/.venv/Scripts/python.exe -m pytest -q tests/test_phase16_las_import.py tests/test_plan300_domain_crud.py` → 14 passed；入口文档已同步至 PLAN-600—700。
- **遗留边界**：内容校验是轻量段标记检查，不等同完整 LAS 规范校验；服务器路径导入仍按部署侧路径权限治理。

### PLAN-690 产物 SHA256 校验和

- **实现思路**：产物中心已具备列表、筛选、预览、下载和删除，但缺少文件内容校验依据。本项在不引入签名体系或集中存储的前提下，为每个 chart/code 产物按块计算 SHA256，并在列表 API 与前端详情中暴露，便于下载后人工或脚本核对。
- **修改文件**：`backend/app/api/routes/files.py`、`backend/tests/test_phase16_artifacts.py`、`frontend/src/services/api.ts`、`frontend/src/services/api.test.ts`、`frontend/src/App.tsx`；同步 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/FEATURE_CATALOG.md`、`docs/API.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/TESTING.md`。
- **核心代码变更**：
  - `_sha256_file(path)`：按 1MB 分块读取文件，避免一次性载入大产物。
  - `_artifact_row()`：为每条产物记录增加 `sha256` 字段。
  - `ArtifactInfo.sha256`：前端类型补齐字段。
  - `ArtifactsPage`：详情 meta 区展示 `sha256` 前 12 位摘要。
- **遇到的问题与解决方案**：产物可能变大，不适合一次性读取。解决方式是后端分块计算摘要；本项只暴露哈希，不声称提供防篡改签名或访问控制。Windows 测试中 `write_text()` 落盘换行可能与字面量 LF 不同，测试改为基于真实文件字节计算期望 SHA256。
- **验证状态（2026-07-17）**：`backend/.venv/Scripts/python.exe -m pytest -q tests/test_phase16_artifacts.py tests/test_phase17_artifact_meta.py` → 4 passed；`npm test -- --run src/services/api.test.ts` → 17 passed；`npm run build` 通过；OpenAPI export + breaking check OK（121 operations）。
- **遗留边界**：仍无保留策略和访问控制细分；SHA256 是完整性校验，不是授权或签名机制。

### PLAN-680 产物删除闭环

- **实现思路**：`FUN-109` 已支持产物列表、筛选、预览和下载，但缺少清理入口。本项按最小本地文件闭环实现删除：只删除 `workspace/charts` 或 `workspace/code` 中的指定产物文件，并同步删除 `workspace/artifacts/{kind}_{filename}.json` sidecar metadata；不扩展为保留策略、校验和、访问控制或 Trace/任务记录清理。
- **修改文件**：`backend/app/api/routes/files.py`、`backend/tests/test_phase16_artifacts.py`、`backend/openapi.snapshot.json`、`frontend/src/services/api.ts`、`frontend/src/services/api.test.ts`、`frontend/src/App.tsx`；同步 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/FEATURE_CATALOG.md`、`docs/API.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/TESTING.md`。
- **核心代码变更**：
  - `_artifact_path(kind, filename)`：复用 `_safe_file` 统一 chart/code 路径解析，非法 kind 返回 400。
  - `DELETE /api/v1/files/artifacts/{kind}/{filename}`：存在则删除文件与对应 metadata，不存在返回 404。
  - `deleteArtifact(kind, filename)`：前端服务层封装 DELETE 请求并编码文件名。
  - `ArtifactsPage`：详情操作区增加删除按钮，确认后删除并按当前筛选条件刷新列表。
- **遇到的问题与解决方案**：产物删除容易被误扩展为“清理所有引用”。解决方式是保持单文件语义，确认文案和文档都明确 Trace/任务记录不删除，metadata 仅作为产物 sidecar 随主文件删除。
- **验证状态（2026-07-17）**：`test_phase16_artifacts.py` / `test_phase17_artifact_meta.py` 通过；`src/services/api.test.ts` 通过；`npm run build` 通过；OpenAPI export + breaking check OK。
- **遗留边界**：校验和后由 PLAN-690 完成；仍无保留策略和访问控制细分；删除不可恢复；不清理已存在的外部引用。

### PLAN-670 会话历史删除闭环

- **实现思路**：`FUN-006` 已支持会话列表、搜索、恢复和 Markdown 导出，但聊天侧栏无法清理过期会话。按最小闭环新增本地删除能力：删除仅作用于 `workspace/sessions/{thread}.json`，不清理 Trace、checkpoint、计划历史或 Agent 聚合历史的其他来源，避免把会话 UI 清理误扩展为运行数据清理。
- **修改文件**：`backend/app/memory/session_store.py`、`backend/app/api/routes/agent.py`、`backend/tests/test_phase14_sessions.py`、`backend/openapi.snapshot.json`、`frontend/src/services/api.ts`、`frontend/src/services/api.test.ts`、`frontend/src/App.tsx`、`frontend/src/App.css`；同步 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/FEATURE_CATALOG.md`、`docs/API.md`、`docs/ACCEPTANCE_CHECKLIST.md`。
- **核心代码变更**：
  - `SessionStore.delete_session(thread_id)`：复用既有安全文件名规则定位 JSON，存在则 `unlink()` 并返回 `True`，不存在返回 `False`。
  - `DELETE /api/v1/agent/sessions/{thread_id}`：删除成功返回 `{deleted}`，不存在返回 404。
  - `deleteChatSession(threadId)`：前端服务层封装 DELETE 请求。
  - `ChatHistoryPanel`：增加删除确认按钮，成功后按当前搜索条件刷新列表。
- **遇到的问题与解决方案**：会话删除容易被误解为清理所有运行痕迹。解决方式是在前端确认文案和文档中明确边界：只删除本地会话历史，不清理 Trace 或 checkpoint；Agent 历史聚合会随 session JSON 消失，但其他任务/文件记录不受影响。
- **验证状态（2026-07-17）**：`test_phase14_sessions.py` 通过；`src/services/api.test.ts` 通过；`npm run build` 通过；OpenAPI export + breaking check OK。
- **遗留边界**：当时仍无归档（已由 PLAN-710 闭环）；仍无分页游标和并发控制；删除是本地单文件删除，不提供回收站。

### PLAN-660 Agent 空闲逐出生命周期调度

- **实现思路**：现有 `MultiAgentManager.evict_idle()` 已能按 `AGENT_IDLE_TTL_MINUTES` 释放非 default 的已加载 Workspace Agent，但没有随应用运行自动调用。本项新增轻量后台服务，在 FastAPI lifespan 中启动/停止，周期执行已有逐出逻辑，保持 checkpoint、Workspace 元数据、删除/purge 语义不变。
- **修改文件**：新增 `backend/app/services/agent_idle.py`、`backend/tests/test_plan660_agent_idle_eviction.py`；修改 `backend/app/main.py`；同步 `docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/FEATURE_CATALOG.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/ACCEPTANCE_CHECKLIST.md`。
- **核心代码变更**：
  - `AgentIdleEvictionService.start()`：幂等创建后台任务，按 TTL 推导 60—300 秒检查间隔。
  - `AgentIdleEvictionService.run_once()`：复用 `multi_agent_manager.evict_idle()`，不引入新的逐出判断。
  - `AgentIdleEvictionService.stop()`：应用关闭时取消任务并等待退出。
  - `main.lifespan`：Phase 1 后启动 idle eviction，shutdown 时先停止该后台任务。
- **遇到的问题与解决方案**：如果直接在 `lifespan` 内写循环，会使测试和关闭路径难以单独验证。解决方式是抽出服务类，测试覆盖 `run_once()`、启动幂等与停止清理；生产路径只负责接入生命周期。
- **验证状态（2026-07-17）**：`test_plan660_agent_idle_eviction.py` 通过；相关 Agent 恢复测试通过；相关文件无 lint 诊断。
- **遗留边界**：仍是单进程内存逐出；不会清理 checkpoint、会话 JSON、计划历史或磁盘文件；跨进程统一生命周期不属于本轮。

### PLAN-650 运维阶段文档与验收同步

- **实现思路**：在 PLAN-600—640 业务代码与专项测试均已落地的前提下，对现行 `docs/*.md`（排除 archive）与根 README 做运维阶段验收同步：勾选 PLAN-650；统一最近验证基线为 pytest `206` / Vitest `25` / E2E `8`（沿用既有记录）/`npm run build`；将 Cron history、Heartbeat 持久、渠道路由验签、插件扫描删除、Agent 磁盘发现/purge 从「未排期/[~]」纠偏为已完成或准确部分完成；保留真实 Provider/渠道联调、RBAC、多实例为未排期。
- **修改文件**：`docs/PROGRESS.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/REQUIREMENTS.md`、`docs/FEATURE_CATALOG.md`、`docs/TESTING.md`、`docs/CHANNELS.md`、`docs/SECURITY.md`、`docs/API.md`、`docs/ARCHITECTURE.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/DOCUMENT_INVENTORY.md`、`docs/README.md`、根 `README.md`。不改业务代码、不改 `docs/archive/`、不提交。
- **核心文档变更**：
  - 最近基线统一为：后端 `pytest --collect-only -q` **206** 项（2026-07-17 本会话确认）；前端 Vitest **25**；Playwright E2E **8**（fake，沿用既有记录并注明不必重跑）；`npm run build` 通过。
  - `ACCEPTANCE_CHECKLIST`：Cron history / Heartbeat 持久 / 渠道路由验签 / 插件扫描删除 / Agent 磁盘发现与 purge 按 PLAN-600—640 标为已完成；真实回发、RBAC、多实例仍未排期。
  - `IMPLEMENTATION_PLAN` 阶段 F 与 PLAN-600—650 全部标为已完成；阶段总览表同步。
  - `REQUIREMENTS` / `FEATURE_CATALOG` / `API` / `ARCHITECTURE` / `TESTING` 等纠偏「运行历史仅内存」「Heartbeat 未写回」「路由未验签」等过期缺口。
- **遇到的问题与解决方案**：多处入口仍写 pytest `176`（PLAN-500 当时基线），易与现行 206 混淆。解决方式是现行入口统一写 206，历史实现记录保留「本项完成当时」口径。E2E 按要求不重跑，验收证据注明沿用 2026-07-17 既有 8 项记录。
- **验证状态（2026-07-17）**：`backend/.venv/Scripts/python.exe -m pytest --collect-only -q` → **206 tests collected**；前端 Vitest 25 passed、`npm run build` 通过（父会话实测）；Playwright E2E 8 项沿用既有记录；无业务代码与 archive 改动。
- **遗留边界**：云端 Actions/required checks、真实 Provider/渠道联调、RBAC/多实例/数据库事务仍未排期；Store memory、飞书 encrypt 解密等边界见各 PLAN 遗留说明。

### PLAN-640 Agent 磁盘发现与删除清理

- **实现思路**：`list_agents` 冷启动扫描 `agents_root` 子目录，跳过 `.deleted`，保证 default 始终在册，仅注册元数据不强制 build graph；删除默认保持 tombstone（目录+checkpoint 保留，列表不可见）；显式 `purge=true` 时 `shutil.rmtree` 工作区并经 `CheckpointProvider.purge` 关闭/删除该 Agent SQLite（含 wal/shm），写 `.purged/{id}` 供 resume 区分「已清除」与「从未存在」；前端删除确认二段选择仅注销/彻底清除。
- **修改文件**：`backend/app/agents/multi_agent_manager.py`；`backend/app/core/checkpoint.py`；`backend/app/api/routes/agents.py`；`backend/app/services/execution_resume.py`；`frontend/src/services/api.ts`；`frontend/src/App.tsx`；新增 `backend/tests/test_plan640_agent_disk_purge.py`；更新 `backend/openapi.snapshot.json`；同步 `docs/{PROGRESS,IMPLEMENTATION_PLAN,API,FEATURE_CATALOG,REQUIREMENTS,ACCEPTANCE_CHECKLIST,ARCHITECTURE,TESTING}.md`；顺带修正 `test_phase5_agents`/`test_plan130` 异步删除与 resume 状态码。
- **核心代码变更**：
  - `MultiAgentManager._discover_disk` + `list_agents`/`get_workspace` 磁盘发现；`delete(..., purge=)` 异步；purge 写 `.purged` 标记。
  - `CheckpointProvider.purge(agent_id)`：关闭 saver 后仅删除 `database_path` 派生路径（`relative_to(sqlite_path)` 校验）。
  - `DELETE /agents/{id}`：query/body `purge`；响应含 `purged`/`checkpoint_retained`。
  - `resolve_agent_for_resume`：tombstone/purge → 409；未知 Agent 仍 404。
  - 前端：`deleteAgent(id, {purge})`；AgentsPage 确认「仅注销 / 彻底清除」。
- **遇到的问题与解决方案**：若 resume 路径把所有未注册一律映射为 409，会破坏「未知 Agent → 404」。解决方式是用 `.purged/{id}` 与 `.deleted` 区分已清除/已注销与从未存在。全量 TestClient lifespan 会关闭全局 checkpoint provider，专项 API 测试改为直接调用路由函数。
- **验证状态**：`test_plan640_agent_disk_purge.py`（7）+ `test_phase5_agents.py` + `test_plan130_multi_agent_plan.py` + `test_plan110_checkpoint.py` 通过；OpenAPI export/breaking OK；前端 `npm run build` 通过；全量 pytest 见顶部基线。本机 2026-07-17 复验：上述 24 条 pytest 全绿；`frontend npm run build` 通过。
- **遗留边界**：`.purged` 仅语义标记不恢复数据；idle 逐出后由 PLAN-660 接入生命周期；purge 不清理会话 JSON/计划历史等非 checkpoint 旁路数据。文档/验收同步见 PLAN-650，会话删除见 PLAN-670。

### PLAN-630 插件扫描与删除治理

- **实现思路**：复用 `SkillScanner` 对插件源目录/已安装目录做与技能同级的静态扫描；安装时 copy 前扫描，失败则 400 且不落盘、不写入 `ENABLED_PLUGINS`；提供按需扫描与 DELETE 卸载（清目录、从启用列表移除并写 `.env`、reload 注册表）；路径名禁止穿越。
- **修改文件**：`backend/app/api/routes/plugins.py`；`frontend/src/services/api.ts`；`frontend/src/components/PluginsManager.tsx`；新增 `backend/tests/test_plan630_plugin_scan_delete.py`；同步 `docs/{PROGRESS,IMPLEMENTATION_PLAN,API,FEATURE_CATALOG,REQUIREMENTS,ACCEPTANCE_CHECKLIST,SECURITY,TESTING}.md`。
- **核心代码变更**：
  - `POST /plugins/install`：源目录与安装副本双扫描；不安全返回结构化 `{message,safe,findings}`，危险插件不得静默安装/自动启用。
  - `GET /plugins/{name}/scan-report`、`POST /plugins/scan`：对齐 skills 扫描形态。
  - `DELETE /plugins/{name}`：`shutil.rmtree` + `_set_enabled_plugin(False)` 写 `.env` + `reload_plugins()`；不存在 404。
  - `_safe_plugin_dir`：拒绝 `.`/`..`/分隔符及解析后逃逸 `plugins_dir` 的名字。
  - 前端：扫描报告展示、删除确认；`api.ts` 补齐 `fetchPluginScanReport`/`scanPlugin`/`deletePlugin`。
- **遇到的问题与解决方案**：HTTP 客户端会把字面量 `..` 规范化导致路由 404；以 `%2e%2e` 与 `_safe_plugin_dir` 单测覆盖真正的路径治理。安装失败后若已 copy，回滚删除目标目录，避免半安装残留。
- **验证状态**：`test_plan630_plugin_scan_delete.py` + `test_phase10_plugins.py` 通过；前端 `npm run build` 通过。
- **遗留边界**：扫描仍为正则静态提示（误报/漏报）；手动 `PUT .../enabled` 不二次强制扫描门禁；启用后仍是进程内 import，无 OS/容器沙箱。

### PLAN-620 渠道 webhook 验签接入

- **实现思路**：在 `_handle_webhook` 解析 JSON 之前读取 raw body 并调用 `channel.verify_signature(headers, body)`；未配置平台密钥时放行并返回/记录 `signature=skipped`；配置了密钥则强制校验，失败 401。同时豁免 `ApiSecurityMiddleware` 对 `/api/v1/gateway/*/webhook` 的 API Token/JWT 要求，避免与平台回调冲突，形成「中间件 HTTP 鉴权」与「平台 webhook 验签」两层边界。
- **修改文件**：`backend/app/api/routes/gateway.py`、`backend/app/api/schemas.py`、`backend/app/middleware/api_security_mw.py`、`backend/app/core/config.py`、`backend/app/services/gateway/base.py`、`channels/{dingtalk,feishu,qq,telegram}.py`、`manager.py`、`backend/.env.example`；新增 `backend/tests/test_plan620_webhook_signature.py`；`docs/{PROGRESS,IMPLEMENTATION_PLAN,CHANNELS,SECURITY,API}.md`。
- **核心代码变更**：
  - 钉钉：`timestamp`/`sign` HMAC-SHA256（既有算法接入路由）。
  - 飞书：校验 body `token` 或 v2 `header.token` 与 `FEISHU_VERIFICATION_TOKEN`；无 encrypt key 配置，不实现加密事件解密。
  - QQ：`Authorization: Bearer <QQ_WEBHOOK_SECRET>` 或 OneBot `X-Signature: sha1=<hmac>`。
  - Telegram：新增 `TELEGRAM_WEBHOOK_SECRET`，比对 `X-Telegram-Bot-Api-Secret-Token`。
  - 响应增加 `signature: verified|skipped`。
- **遇到的问题与解决方案**：开启 `API_TOKEN` 后平台无法带自定义鉴权头。解决方式是中间件豁免 gateway webhook，安全依赖各渠道验签；本地未配密钥时明确 `skipped` 而非静默“已鉴权”。
- **验证状态**：`test_plan620_webhook_signature.py` + 既有 gateway/access/security/channels 相关测试通过。
- **遗留边界**：未做飞书 encrypt 解密、钉钉时间戳窗口/重放保护、真实四渠道联调；QQ 仅覆盖常见 Bearer/HMAC 形态。

### PLAN-600 Cron 运行历史持久化

- **实现思路**：在既有 `cron_jobs.json` 之外增加独立 `cron_history.json`；运行开始与结束时落盘，服务重建后加载并截断到 500 条。
- **修改文件**：`backend/app/services/cron_service.py`；新增 `backend/tests/test_plan600_cron_history.py`；计划/进度文档。
- **核心代码变更**：`CronService` 支持 `history_path`；`_load_history`/`_persist_history`；`_run_job` 在插入 running 记录与终态写回时都持久化。
- **遇到的问题与解决方案**：历史与 job 配置混存会放大写冲突风险。解决方式是分文件持久，保持 API `/tasks/cron/history` 不变。
- **验证状态**：`test_plan600_cron_history.py` + `test_phase9_scheduler.py` 通过。

### PLAN-610 Heartbeat 配置持久化与热更新

- **实现思路**：PUT 改为调用 `HeartbeatService.update()`，写入 `.env` 的 `HEARTBEAT_*` 并重调度 APScheduler；关闭时移除 job。
- **修改文件**：`backend/app/services/heartbeat.py`、`backend/app/api/routes/cron.py`；新增 `backend/tests/test_plan610_heartbeat_persist.py`。
- **核心代码变更**：`update()` + `_persist_settings()` + `_apply_schedule()`；响应增加 `persisted: true`；`start()` 可接收外部 scheduler 并按当前配置应用。
- **遇到的问题与解决方案**：原先直接改进程内 settings，重启回退。解决方式是复用 `update_env_file`，并在禁用时显式 `remove_job`。
- **验证状态**：专项测试覆盖 env 落盘、启停重调度、路由委托；与 phase9 调度测试一并通过。

明确边界：

- 工具审批已用真实 LangGraph 测试证明批准时原 handler 单次执行、拒绝时零执行，并以稳定 `agent/thread/tool_call` key、`pending→resuming→approved|rejected` 状态机阻止重复/并发裁决；恢复失败转不可自动重试的 `resume_failed`。
- 单机内并发裁决已互斥，但本地审批 JSON 与工具所写外部资源没有跨资源事务；进程若在工具副作用完成后、审批终态写回前崩溃，只能标记结果不确定，不能宣称分布式 exactly-once。
- 多 Agent 计划已使用服务端完整 ref、精确 pending 历史和统一 resolver；真实 SQLite/API 测试覆盖同 thread 双 Workspace、approve/edit/reject、reload/evict/restart、删除/错误 Agent 和 default 兼容。PLAN-200 又将同一 Agent 标识扩展到 SSE。
- SSE v1 已统一 Agent、命令、语言、source、session、中断与单进程取消语义；前端停止先 abort 本地读取，再请求服务端确认取消。
- task、同步/SSE 与渠道 Agent 子任务使用进程内 `RunRegistry`；这不提供跨进程、服务重启后或多副本之间的取消能力。
- SQLite checkpoint 只支持当前单机部署边界，不代表多实例共享恢复；会话 JSON、计划历史和审批历史仍不等于 checkpoint。
- 前端现有 25 项组件/协议测试与关键模块覆盖率门槛；浏览器 E2E（PLAN-410）与 CI workflow（PLAN-420）已建立；PLAN-600—700 运维闭环已完成；真实 Provider/渠道仍非默认门禁。

### PLAN-500 文档持续治理（本轮闭环）

- **实现思路**：在 PLAN-100—420 均已实现并勾选的前提下，对现行 `docs/*.md`（排除 archive）与根 README 做全量审阅：状态标记、测试基线、PLAN 勾选、REQ/FUN、API/页面验收、相对链接、日期与过度宣称；统一最近验证基线；纠偏过期完成率与虚构/过期材料描述；未排期项保持未完成并写明映射；本轮形成可重复执行的治理闭环，而非一次性“写完即停”。
- **修改文件**：`docs/DOCUMENT_INVENTORY.md`、`docs/README.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/PROGRESS.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/TESTING.md`、`docs/REQUIREMENTS.md`、`docs/FEATURE_CATALOG.md`、根 `README.md`。不改业务代码、不改 `docs/archive/`、不提交。
- **核心文档变更**：
  - 最近基线统一为：后端 pytest `176`；前端 Vitest `25`；Playwright E2E `8`（fake）；`npm run build` 通过；CI workflow 已落盘，云端 Actions 待启用（无 `.git`）。
  - `DOCUMENT_INVENTORY` 从“无前端测试/无 CI/166”纠偏为现行 Vitest/E2E/CI/OpenAPI 快照与 176 基线；补登记 `test_plan300_*`、`ci-local.*`、`playwright.config.ts`。
  - `ACCEPTANCE_CHECKLIST` 确认 PLAN-100—420 对应项为已完成；新增「未排期项映射」表（RBAC、多实例、真实 Provider/渠道默认门禁等）；文档治理行映射 PLAN-500。
  - `TESTING.md` 矩阵“实际收集数”从过期 166 改为 176；根 README 领域行从“缺完整 CRUD”改为单实例 CRUD 闭环；入口/状态/需求/功能头注同步。
  - PLAN-500 在计划/进度中标记为本轮闭环已完成，并注明可持续再执行。
- **遇到的问题与解决方案**：多处历史记录仍用“最近”指向 166，易被误认为现行基线；台账与状态报告残留 PLAN-400/410 之前的缺口表述。解决方式是现行入口统一写 2026-07-17 基线，历史实现记录改为“本项完成当时/当时基线”，并保留 fake 与云端未启用边界。
- **验证状态（2026-07-17）**：`pytest --collect-only -q` 汇总 176；前端自有 `*.test.*` 5 个、E2E 规格存在；`.github/workflows/ci.yml` 与 `scripts/ci-local.*` 存在；现行文档相对链接抽检无断链；未宣称云端 Actions 已跑通或生产就绪；无业务代码与 archive 改动。
- **遗留边界**：云端 Actions/required checks、真实 Provider/渠道、RBAC/多实例仍未实现；后续代码或契约变化时应再跑 PLAN-500 检查清单。

### PLAN-420 持续集成与契约门禁

- **实现思路**：以 `.github/workflows/ci.yml` 为真源，在干净 `ubuntu-latest` 上并行跑后端/前端/E2E/Compose/安全扫描；本地用 `scripts/ci-local.ps1` / `ci-local.sh` 复现主门禁。
- **Jobs**：`backend`（ruff、mypy、OpenAPI breaking、pytest）、`frontend`（Vitest、coverage、build）、`e2e`（Playwright chromium + 系统依赖）、`compose`、`security`（pip-audit + npm audit high+）、可选 `gitleaks`（非阻断）。
- **OpenAPI**：快照 `backend/openapi.snapshot.json`；破坏性变更（删路径/方法、新增必填、删 2xx）失败，描述/示例变更不失败。
- **Required checks**：推送到 GitHub 并跑通后，在 Branch protection 勾选上述主 job 名称；详见 `IMPLEMENTATION_PLAN.md` PLAN-420 与 `DEPLOYMENT.md`。
- **验证状态（2026-07-17）**：本机等价命令 ruff/mypy/OpenAPI/pytest `176`、Vitest `25`、coverage、build、E2E `8`、`docker compose config`、`pip-audit`（无已知漏洞）、`npm audit`（0）通过；同日复验上述门禁仍全部通过；**workflow 已落盘，云端 Actions 待仓库启用**（当前无 `.git`）。
- **遗留边界**：不证明真实 Provider/渠道；镜像 CVE 扫描未做阻断；gitleaks 默认观察；branch protection 需在远程仓库手工启用。

### PLAN-410 浏览器 E2E

- **实现思路**：用 Playwright Chromium 覆盖关键控制台路径；默认门禁用 context 级 route fake Provider/后端与每测例隔离 store，不依赖真实 LLM；真实 Provider/渠道放入 `manual` 项目，需显式 `--project=manual-real-provider`。
- **依赖版本**：npm 实际解析 `@playwright/test` `1.61.1`（当前 registry 最新兼容版；仅 `devDependencies`）；浏览器二进制经 `npx playwright install chromium` 安装。
- **测试基础设施**：`playwright.config.ts` 配置 chromium 项目、`VITE_E2E_FAKE=1` 关闭 Vite API 代理、失败保留 trace/screenshot/video、失败附加 browser-logs 与 fake-backend 快照；脚本 `npm run test:e2e`（默认门禁）与 `npm run test:e2e:manual`（不进 PR 门禁）；可选 `backend/scripts/e2e_fake_server.py` 提供隔离 `WORKSPACE_DIR` + FakeAgent。
- **场景（8）**：登录门（CONSOLE_PASSWORD）、default Agent 对话回声、nondefault `/plan` ExecutionRef 确认、工具审批批准、流式停止+服务端取消、任务深链取消、井/日报 CRUD 与 `well_id` 深链、设置/Agent 深链刷新；每测例独立 store，无固定 sleep。
- **验证状态（2026-07-17）**：`npm run test:e2e` 8 passed（chromium）；`npm test -- --run` 5 files/25 passed；`npm run build` 通过；后端 `.\.venv\Scripts\python.exe -m pytest -q` 全量 `176` 通过。PLAN-420 后续已完成。
- **遗留边界**：默认套件不证明真实 Provider/渠道联通。

### PLAN-300 领域 CRUD、关系约束与导航

- **实现思路**：保留单实例 JSON 架构，以最小改动补齐关联实体契约；把 `well_id` 校验放入 DomainStore 同一把进程内锁，在删除井前统一统计领域记录和产物侧车依赖。默认拒绝有依赖的井删除，不做隐式级联。
- **修改文件**：修改 `backend/app/domain/store.py`、`las_importer.py`、`backend/app/api/routes/domain.py`、`frontend/src/services/api.ts`、`frontend/src/App.tsx`；新增 `backend/tests/test_plan300_domain_crud.py`；同步计划、需求、功能、架构、API、测试、状态与验收文档。
- **核心代码变更**：井段新增单条 GET；日报、参数、LAS 补齐 get/update/delete。关联创建/更新的井不存在时返回结构化 404；井存在井段/日报/参数/LAS/产物时删除返回结构化 409。LAS 删除只清理匹配 `{las_id}.json` 的托管曲线文件和无其他记录引用的 `las_uploads` 文件，外部导入源路径永不删除。
- **存储可靠性**：DomainStore 新写入 `schema_version=1` 并兼容旧无版本 JSON；所有读改写由 `RLock` 保护，写前复制 `.bak`，同目录临时文件 flush/fsync 后 `os.replace`，替换失败保留原文件并清理临时文件。该方案不扩展为跨进程锁或数据库迁移。
- **前端**：service/types 补齐操作；井详情支持编辑、依赖保护删除、井段编辑/删除和到日报/参数/LAS/产物的关联入口，井数据列表区直接暴露日报/参数/LAS。三类记录页支持井筛选、详情/编辑、删除确认、错误展示，来自井详情的 `well_id` 查询参数作为初始筛选并在 CRUD 后保留。
- **验证状态**：`test_plan300_domain_crud.py` 10 项覆盖四类关联 CRUD、404、缺失井、井删除 409、LAS 文件安全策略、旧 JSON、备份/原子替换失败和并发写；项目 `.venv` 全量收集并通过 `176` 项 pytest；前端 `npm run build` 通过，编辑器诊断无新增错误。
- **该项完成时的遗留边界**：数据库事务/迁移、多实例一致性、前端组件测试和 E2E 不属于本项；当时 PLAN-400、PLAN-410、PLAN-420 保持未勾选，PLAN-400 后续已完成。

### PLAN-400 前端组件与协议测试

- **实现思路**：使用 npm 安装实际兼容的 Vitest/jsdom/Testing Library，测试包全部放在 `devDependencies`；复用纯 SSE parser，并把流式 fetch、envelope 规范化、abort 与服务端取消提取为 `chatStream.ts` 最小协议模块。
- **测试基础设施**：新增 jsdom setup、JSON/文本/分块流/deferred fetch mock、`test`/`test:coverage` 脚本和 V8 coverage 配置，不引入真实 Provider、渠道或浏览器 E2E。
- **覆盖重点**：5 个文件 25 项覆盖 SSE 多行/CRLF/分块/done once/error，计划完整 ExecutionRef 和失败可见，审批 pending/resuming/不可恢复/重复点击，Chat 停止，领域更新/删除请求，鉴权及网络错误；无 snapshot 用例。
- **覆盖门槛**：`sse.ts` 为 statements/lines 95%、branches 85%、functions 100%；`chatStream.ts` 为 statements/lines 75%、branches 65%、functions 80%。实测合计 statements 97.19%、branches 82.05%、functions/lines 100%。
- **问题与解决**：聚合 `api.ts` 超过 1300 行，整文件百分比会诱导低价值补测；改为提取风险集中的独立协议模块并设置有意义门槛，API 关键请求仍由行为断言覆盖。Vitest `exclude` 含 `e2e/**`，与 Playwright 规格隔离，保证 `npm test -- --run` 只跑组件/协议单测。
- **验证状态**：`npm test -- --run` 5 files/25 tests passed；`npm run test:coverage`、`npm run build` 和后端全量 176 项 pytest 通过。
- **遗留边界**：本项当时不包含真实浏览器 E2E 或 CI workflow；PLAN-410、PLAN-420 后续均已完成。

## 二、历史 Phase 40—46 摘要

下列阶段保留为历史实现摘要，完整文件级记录见归档。`[x]` 仅表示相应代码改动曾完成，不覆盖本文件顶部列出的系统级缺口。

### Phase 40：MCP Recover 指标

- [x] `MCPManager` 记录 reload/recover 的 success/failed 计数。
- [x] `/monitor/metrics` 输出 `boetclaw_mcp_recover_total{result}`。
- [x] 增加 MCP 与 metrics 回归测试。
- **边界**：证明本地 reload 计数，不证明真实 MCP 服务长期恢复能力。

### Phase 41：Metrics 核心计数

- [x] 基于 Trace 事件聚合 Agent 运行、工具调用、Guard 拦截和 Provider 重试计数。
- [x] 保持原任务、审批、网关和 MCP 指标兼容。
- **边界**：事件聚合是轻量近似，不是标准 Prometheus client registry。

### Phase 42：Agent 运行耗时 Histogram

- [x] 按 `run_id` 配对 `AGENT_START`/`AGENT_END`。
- [x] 输出固定 bucket 的 `boetclaw_agent_run_duration_seconds`。
- [x] 忽略缺失配对、非法时间和负耗时事件。

### Phase 43：Slash 命令 i18n

- [x] 新增 zh/en 字典和翻译 helper。
- [x] `/help`、`/new`、`/clear`、`/stop`、`/restart` 接入请求级语言。
- **边界**：`/stop` 的本地化文案不代表执行取消已经实现。

### Phase 44：Accept-Language 覆盖

- [x] `/agent/chat` 支持 `Accept-Language`。
- [x] 语言优先级为 body `lang` > header > 配置默认值。
- **边界**：主要覆盖 slash command，不是全量 UI/Agent 输出国际化。

### Phase 45：计划状态闭合审计

- [x] 曾修正旧进度中 Phase 14—17 标题与子项勾选不一致。
- **纠偏**：后续 2026-07-15 代码审计发现多项语义缺口，因此本文件不沿用“全量任务均完成”的结论。

### Phase 46：ToolGuard 提示 i18n

- [x] ToolGuard 安全拦截和用户拒绝提示接入 zh/en 字典。
- [x] 使用 ContextVar 传递请求语言并增加回归测试。
- **边界**：该历史阶段当时未修复审批关联、持久 checkpoint 或 fail-open；关联与 fail-open 后由 PLAN-100 修复，持久 checkpoint 后由 PLAN-110 完成。

## 三、本轮文档实现记录

### PLAN-100 统一可恢复运行标识

- **实现思路**：由后端从 LangGraph Interrupt 生成不可变 `ExecutionRef(agent_id, thread_id, checkpoint_ns, interrupt_id, interrupt_type)`，响应、历史、审批和前端只传递该引用；共享底层 graph resume adapter，但计划确认与工具审批分别建服务并校验类型、引用和 pending 状态。
- **修改文件**：新增 `backend/app/core/execution_ref.py`、`backend/app/services/execution_resume.py`、`plan_resume.py`、`approval_resume.py`、`backend/tests/test_plan100_execution_ref.py`；修改 Agent 运行时、API schema/路由、运行上下文、计划/ToolGuard 中间件、计划/审批 JSON 模型、相关旧测试，以及 `frontend/src/services/api.ts`、`ChatPanel.tsx`、`PlanConfirm.tsx`、`ApprovalCard.tsx`、`App.tsx`。
- **核心代码变更**：同步默认/Workspace invoke 返回 `execution_ref + payload` 并保留 `interrupted/todos`；旧 default-agent thread-only 请求只做一周期兼容；错误/过期 ref 不调用 graph；审批 resume 成功后才落 approved/rejected，运行异常或适配器报告不可恢复时落 `resume_failed/error`；旧缺 ref JSON 只读；删除 ToolGuard interrupt 异常自动 approve，图外异常明确失败且不执行 handler；前端保存服务端 ref、展示恢复错误并禁用缺 ref 审批。
- **遇到的问题与解决方案**：中间件创建审批时尚拿不到 LangGraph 生成的 interrupt ID。解决方式是先把服务端生成的 approval ID 放入 interrupt payload，`ainvoke` 返回真实 Interrupt 后再原子绑定完整 `ExecutionRef` 并注册当前进程内待恢复图；无法绑定时直接失败，不放行工具。根图 `checkpoint_ns` 按 LangGraph 约定显式保存空字符串，而不是省略字段。
- **验证状态**：专项测试覆盖不可变模型、对象/字典解析、错误 ref 不 resume、审批状态顺序、运行异常与适配器校验失败状态、旧 JSON、fail-closed、计划/审批类型隔离；本项完成当时后端全量 `159 passed`；前端 `npm run build` 通过；编辑器诊断无新增错误。
- **当时遗留边界**：持久 checkpoint、工具审批闭环和多 Agent 计划确认已分别由 PLAN-110/120/130 完成；前端组件测试后由 PLAN-400 完成，E2E 后由 PLAN-410 完成。

### PLAN-110 Checkpoint 持久化

- **实现思路**：引入应用统一持有的 `CheckpointProvider`，默认使用 `langgraph-checkpoint-sqlite==3.1.0` 的 `AsyncSqliteSaver`，按 `agent_id` 的 SHA-256 摘要生成独立 SQLite 文件；默认 Agent 与 Workspace Agent 只向 provider 获取 saver。`GraphResumeAdapter` 保留进程内 registry 快速路径，registry 丢失时按完整 `ExecutionRef` 解析并重建原 Agent，再从 checkpoint task 中核对 interrupt ID/type 后执行 `Command(resume=...)`。`memory` 仅作为显式降级，不做隐式故障回退。
- **修改文件**：新增 `backend/app/core/checkpoint.py`、`backend/tests/test_plan110_checkpoint.py`；修改 `backend/requirements.txt`、`backend/app/core/config.py`、`backend/app/core/startup.py`、`backend/app/main.py`、`backend/app/core/agent.py`、`backend/app/agents/multi_agent_manager.py`、`backend/app/services/execution_resume.py`、`backend/app/security/approval.py`、`backend/app/api/routes/agents.py`、`backend/app/api/routes/monitor.py` 及相关测试。
- **核心代码变更**：默认配置为 `CHECKPOINT_BACKEND=sqlite`、`CHECKPOINT_SQLITE_PATH=./workspace/checkpoints`；provider 初始化目录并调用官方 `setup()`，并发按 Agent 加锁，lifespan 关闭所有异步连接；Agent reload/idle eviction/注销只重建或移除实例，不清理 checkpoint。health 返回 backend、persistent、`supports_restart_resume`、warning、SQLite 路径、打开 saver 数和错误；初始化失败时 health 降级、Agent 保持未就绪。memory 重启时旧 pending 审批显式过期，SQLite 模式则保留 pending，交由恢复时验证。
- **遇到的问题与解决方案**：仅持久化审批/计划 JSON 无法重建 LangGraph 中断栈，因此改用官方 SQLite checkpointer；仅依赖 adapter registry 会在重启后丢失，因此增加 resolver 重建 graph 并读取 `aget_state().tasks[].interrupts` 校验真实 ID/type；相同 thread 在不同 Agent 下可能串线，因此采用每 Agent 独立数据库而非共享文件；SQLite 初始化失败不能静默切到 memory，因此记录 provider 错误并由 health 明确降级。
- **验证状态**：`test_plan110_checkpoint.py` 11 项覆盖 provider 重建后读取、默认 Agent 实例重建后恢复、同 thread 跨 Agent 隔离、memory 降级状态、非法 backend、连接关闭、缺失/类型不匹配 interrupt、审批不可恢复状态及 SQLite/memory 重启 pending 行为；本项完成当时后端全量 pytest `159 passed`；前端 `npm run build` 通过。
- **遗留边界**：SQLite 是单机持久化方案，不支持多实例共享写入、协调或高可用；checkpoint 数据迁移、在线压缩/清理和独立清理 API 尚未提供。工具审批与多 Agent 计划确认后由 PLAN-120/130 完成。

### PLAN-120 工具审批端到端恢复

- **实现思路**：以服务端运行上下文中的 `agent_id + thread_id + tool_call_id` 生成稳定幂等 key；LangGraph 节点重放时复用同一审批。裁决先在进程内锁保护下原子抢占为 `resuming`，再恢复原 graph，只有 graph 成功后进入 `approved/rejected`。
- **修改文件**：修改 `backend/app/security/approval.py`、`middleware/tool_guard_mw.py`、`services/approval_resume.py`、`services/execution_resume.py`、审批 API schema/route、相关旧测试；新增 `backend/tests/test_plan120_tool_approval.py`；更新 `frontend/src/components/ApprovalCard.tsx`、`frontend/src/services/api.ts` 及本轮需求、功能、架构、API、安全、测试、状态、验收和计划文档。
- **核心代码变更**：审批加入 `idempotency_key/decision/updated_at` 与 `pending→resuming→approved|rejected`、`resuming→resume_failed` 状态；重复/并发裁决只有一个请求可进入 graph；resume 恢复原 Agent/thread 上下文，默认与非默认 Agent 均由 `ExecutionRef` resolver 路由；审批 ID、完整 ref、类型、状态和 decision 均在恢复前校验；拒绝路径不调用 handler，中断不可用继续 fail-closed。
- **前端**：ApprovalCard 展示 Agent、thread、tool、参数、风险、ExecutionRef、状态和错误；缺 ref、处理中和终态不可操作；本地提交集合阻止重复点击。
- **验证状态**：真实最小 LangGraph 测试覆盖 approve handler 一次、reject 零次、节点重放审批不重复、重复/并发裁决不重复、恢复失败终态、服务与 adapter 重建后 SQLite 恢复及非默认 Agent resolver；本项完成当时后端全量 `159 passed`，前端 `npm run build` 通过，编辑器诊断无新增错误。
- **遗留边界**：`resume_failed` 是安全优先的终态，不自动重试。审批 JSON、LangGraph SQLite checkpoint 与工具副作用不共享事务；进程在工具副作用完成后、graph 返回或审批终态写回前崩溃时，副作用结果可能不确定，系统只能阻止自动重试，不能提供跨资源或分布式 exactly-once。

### PLAN-130 多 Agent 计划确认

- **实现思路**：以服务端签发的不可变 `ExecutionRef` 作为计划 pending 的唯一身份；计划历史保存顶层 Agent/thread/interrupt 字段和完整 ref，并以精确 ref 校验尚未处理。同步非默认调用与 resume 复用严格 resolver，任何未知、已删除或不匹配引用均返回 4xx，不回退 default。
- **修改文件**：新增 `backend/app/agents/resolver.py`、`backend/tests/test_plan130_multi_agent_plan.py`；修改 `multi_agent_manager.py`、`execution_resume.py`、`plan_resume.py`、`plan_history_store.py`、Agent API schema/route，以及 `frontend/src/components/PlanConfirm.tsx`、`ChatPanel.tsx`；同步计划、需求、功能、API、架构、测试、状态和验收文档。
- **核心代码变更**：`PlanConfirmResponse` 显式返回原 `agent_id/thread_id/interrupt_id/execution_ref`；history 支持 `agent_id + thread_id` 联合查询并兼容旧 JSON；非默认 Agent 删除写 tombstone，保留 checkpoint 但禁止残留目录恢复；adapter 对非默认内存注册图也先检查 Agent 存续；前端 pending 保存原响应 ref，切换下拉 Agent 不改变提交目标，失败错误保留可见。
- **遇到的问题与解决方案**：仅按 checkpoint interrupt ID 校验不足以阻止同构 Workspace 同 thread 的跨 Agent 伪造引用，因为不同图可能产生相同结构化中断。解决方式是在恢复前再核对服务端计划历史中的精确完整 ref 和 pending 状态。删除后内存 adapter 仍可能持有原 graph，故 resolver 存续校验必须先于注册表快速路径。
- **验证状态**：`test_plan130_multi_agent_plan.py` 使用真实最小 LangGraph、每 Agent SQLite saver 和 ASGI API，验证双 Workspace 同 thread 的 approve/edit/reject 不串线，跨 Agent ref 失败，history 联合筛选，reload/evict/provider 重建恢复，删除/未知 Agent 4xx，以及唯一 default pending 的 thread-only 兼容和旧 JSON。本项完成当时后端全量 `159 passed`；前端 `npm run build` 通过；编辑器诊断无新增错误。
- **遗留边界**：SQLite 和 JSON 历史仍是单实例方案；Workspace 磁盘目录/checkpoint 删除策略、启动时完整列表发现、前端组件/E2E 自动化分别不属于本项。该项当时未改流式路径，后由 PLAN-200 完成统一。

### PLAN-200 同步与流式统一

- **实现思路**：只抽取请求入口和运行结果收尾两处共享能力。`prepare_chat()` 统一 thread、Agent、source、语言、命令与 trace/run；`invoke_agent()`/`stream_agent()` 共用中断解析、ExecutionRef 注册、计划历史和审批绑定，避免重写 Agent 工厂或恢复服务。
- **修改文件**：新增 `backend/app/services/chat_orchestration.py`、`backend/tests/test_plan200_stream_chat.py`、`frontend/src/services/sse.ts`；修改 `backend/app/agents/runtime.py`、`backend/app/api/routes/agent.py`、`frontend/src/services/api.ts`、`frontend/src/components/ChatPanel.tsx`，并同步计划、需求、功能、API、架构、测试、状态与验收文档。
- **核心代码变更**：同步/SSE 复用严格 resolver；default/Workspace graph 都通过自身 `astream` 真正流式；`/plan` 在两路径统一清洗并设置规划态，其他 slash command 返回 command 事件且不进 LLM；SSE v1 envelope 固定携带 `event/data/version/thread_id/agent_id/trace_id/run_id`，成功/命令/中断只发一次 done，错误不发 done；成功和中断只记录一轮 session，命令/错误不记录。
- **前端**：删除 `/plan` 与非默认 Agent 强制同步；请求发送 `agent_id/source/lang`；纯函数 parser 支持多行 data、CRLF、分块边界及旧 SSE；HTTP 错误、error 事件与无 done 断流均显示；plan/tool interrupt 分别复用 PlanConfirm/ApprovalCard。
- **验证状态**：`test_plan200_stream_chat.py` 6 个收集用例以 ASGI/fake Agent 覆盖 default/nondefault、同步共享 resolver、plan interrupt、slash command、lang/source、session、error 和 done once；本项完成当时后端全量 `159 passed`；前端 `npm run build` 通过；编辑器诊断无新增错误。
- **后续状态**：该项未增加前端测试框架，SSE 纯函数仍由 TypeScript/Vite 构建验证，自动化协议单测归 PLAN-400；当时遗留的客户端/服务端取消已由下述 PLAN-210 完成。

### PLAN-210 任务与运行真正取消

- **实现思路**：建立最小单进程 `RunRegistry`，统一 task、同步/SSE 和渠道 Agent 子任务的活动运行索引、取消令牌与安全状态转换；终态只清理活动索引和 task 引用，保留有界终态记录以支持明确、幂等响应。
- **修改文件**：新增 `backend/app/services/run_registry.py`、`backend/tests/test_plan210_cancellation.py`；修改任务/Agent/渠道路由、任务状态存储、可观测事件、应用 shutdown、i18n、前端 API/ChatPanel/CSS，并同步计划、需求、功能、API、架构、测试、状态和验收文档。
- **核心代码变更**：任务不再用 `BackgroundTasks` 启动 Agent，而由注册表创建并持有 `asyncio.Task`；cancel 进入 cancelling 后取消并等待确认，CAS 防止 cancelled 被 completed/failed 覆盖；`/stop` 按 Agent+thread 找活动 run；运行取消 API 同时校验 run/Agent/thread，跨 Agent 同 thread 失败关闭。
- **SSE 与前端**：SSE/同步运行均登记 run，生成器关闭或任务取消进入 cancelled；plan/approval interrupt 正常进入 completed。流控制先 abort，再调用 `POST /api/v1/agent/runs/cancel`，UI 分别展示本地停止和服务端确认结果。
- **遇到的问题与解决方案**：旧任务取消只改 JSON 状态，`BackgroundTasks` 又不暴露可等待的执行句柄；流式本地 abort 也不能证明服务端协程已停止。解决方式是让 `RunRegistry` 统一持有 `asyncio.Task`/取消令牌，以受限状态机和 CAS 协调取消与完成竞态，并由前端在 abort 后调用服务端取消 API 获取确认。
- **验证状态**：`test_plan210_cancellation.py` 7 项覆盖长运行 fake Agent 收到 `CancelledError`、终态保护、重复取消、完成/取消竞态、Agent/thread 隔离、`/stop`、取消端点、interrupt 与 shutdown；本项完成当时后端全量约 `166 passed`；现行最近基线见顶部清单（2026-07-17：pytest `206` / Vitest `25` / E2E `8`）。
- **当时遗留边界**：注册表为单进程内存结构，不支持跨进程/多副本取消或重启恢复活动 task；组件测试后由 PLAN-400 完成，E2E 后由 PLAN-410 完成。

### DOC-001 材料台账

- **实现思路**：先盘点现行文档、历史计划/进度、运行时技能、配置、部署文件和测试材料，按“现行、归档、代码事实来源”分类。
- **修改文件**：新建 `docs/DOCUMENT_INVENTORY.md`。
- **核心文档变更**：登记每份材料用途、问题和处置；建立代码事实来源索引；明确不清理 workspace、虚拟环境、依赖和构建产物。
- **遇到的问题与解决方案**：旧计划/进度大量勾选完成，容易被当作事实。解决方式是规定优先级：源码/配置 > 测试 > 现行文档 > 归档。
- **验证状态**：已核对 `docs/`、部署配置、测试目录和归档文件清单；完成。

### DOC-002 项目状态报告

- **实现思路**：从路由、服务、中间件、前端调用和测试反推真实闭环，不继承旧阶段结论。
- **修改文件**：新建 `docs/PROJECT_STATUS_REPORT.md`。
- **核心文档变更**：记录审批恢复、多 Agent 计划、当时的 MemorySaver、流式分叉、任务假取消、领域 CRUD、前端测试/CI 七类关键缺口；该记录建立当时测试基线为 143 项；其后中间基线曾为约 166/176 项；现行最近基线见顶部清单（206）。
- **遇到的问题与解决方案**：代码“有接口”但语义未闭环。解决方式是按入口—执行—持久化—恢复/查询—测试逐层判断，并将 fake/mock 与真实联通分开。
- **验证状态**：后端、前端构建和 Compose 结果已有执行证据；该项完成当时真实 Provider、渠道和浏览器 E2E 明确标记未验证（其后 PLAN-410 补齐 fake E2E）；完成。

### DOC-003 需求说明

- **实现思路**：把项目定位、角色、范围、功能与非功能需求统一为 `REQ-xxx`，状态只取已实现/部分实现/待实现。
- **修改文件**：重写 `docs/REQUIREMENTS.md`。
- **核心文档变更**：建立 REQ-001—006 总体目标、REQ-100—224 功能需求、REQ-300—310 非功能需求及 REQ-400—405 技术约束；补充验收原则。
- **遇到的问题与解决方案**：旧文档把目标设计写成完成态。解决方式是为每条需求增加事实与边界，尤其将 checkpoint、多 Agent stream、任务取消和领域关系约束标为部分/待实现。
- **验证状态**：与状态报告和代码实现路径交叉核对；完成。

### DOC-004 功能清单

- **实现思路**：以用户可感知能力为单位建立 `FUN-xxx`，映射到 REQ、模块、实现路径、状态和缺口。
- **修改文件**：重写 `docs/FEATURE_CATALOG.md`。
- **核心文档变更**：覆盖 Agent、扩展、技能、多 Agent、安全、任务、调度、渠道、领域、可观测、前端和部署。
- **遇到的问题与解决方案**：一个 REQ 可能对应多个部分能力。解决方式是拆成同步/流式、任务状态/真正取消、Agent 创建/删除等独立 FUN 项，避免平均状态掩盖缺口。
- **验证状态**：FUN 编号与 REQUIREMENTS、API、状态报告一致；完成。

### DOC-005 历史归档

- **实现思路**：保留追溯价值，但把过期长文从现行事实入口移出。
- **修改文件**：新增 `docs/archive/2026-07-15/*_legacy.md`、`IMPLEMENTATION_PLAN_v3_full.md`、`PROGRESS_full.md`。
- **核心文档变更**：保存五份专题整理前快照和完整计划/进度历史；现行文档不再双向维护归档内容。
- **遇到的问题与解决方案**：历史记录包含当时正确、现在过期的判断。解决方式是只读归档并在导航/台账中明确适用日期和事实优先级。
- **验证状态**：归档目录共 7 份文件，现行导航已说明用途；完成。

### DOC-006 架构说明

- **实现思路**：按当前运行结构描述启动、Agent 构建、中间件、同步/流式、恢复、任务、渠道、存储和部署拓扑。
- **修改文件**：重写 `docs/ARCHITECTURE.md`。
- **核心文档变更**：明确默认/非默认 Agent 分叉、当时的 MemorySaver、流式只走默认 Agent、任务取消边界、JSON 存储和前端 History API 路由。
- **遇到的问题与解决方案**：目标架构与当前代码混杂。解决方式是正文只写现状，把数据库、持久 checkpoint、多实例等放入“已知限制与演进方向”。
- **验证状态**：与 `backend/app/core/`、`agents/`、`api/routes/`、`frontend/src/App.tsx` 和部署文件核对；完成。

### DOC-007 API 索引

- **实现思路**：按 Router 分组完整列出 `/api/v1` 路径，但不复制全部 schema。
- **修改文件**：重写 `docs/API.md`。
- **核心文档变更**：补齐认证、会话、计划历史、任务、Cron、Agent、技能、Provider、安全、MCP、插件、渠道、领域、产物和监控端点；每组映射 FUN。
- **遇到的问题与解决方案**：人工文档必然可能落后。解决方式是在顶部和维护规则中明确 `/docs`、`/openapi.json` 为字段、校验与状态码契约真源。
- **验证状态**：路径与 `backend/app/api/routes/*.py` 核对；完成。

### DOC-008 测试说明

- **实现思路**：区分测试文件静态数量、pytest 实际收集数量、构建检查和未覆盖领域。
- **修改文件**：重写 `docs/TESTING.md`。
- **核心文档变更**：建立 24 个后端测试文件矩阵；记录静态约 123 个、实际 122 个及重复测试名原因；列出前端/E2E/CI 缺口和高风险验收用例。
- **遇到的问题与解决方案**：测试函数数与收集数不一致。解决方式是定位 `test_phase15_mcp.py` 重复定义，并同时记录两种口径。
- **验证状态**：该项完成当时记录后端约 `166 passed`，前端当时仅 build；现行基线与前端测试/E2E/CI 见 PLAN-400/410/420/500；完成。

### DOC-009 安全说明

- **实现思路**：描述已实现控制，同时把 fail-open、审批关联、webhook 验签、明文密钥和单进程限流列为边界。
- **修改文件**：重写 `docs/SECURITY.md`。
- **核心文档变更**：详述 ToolGuard 决策、审批持久化、Plan Gate、Token/JWT、限流、渠道白名单、技能与插件风险。
- **遇到的问题与解决方案**：安全代码存在但某些路径不能提供预期保障。解决方式是明确“应用层规则不是沙箱”“历史可审计不等于图可恢复”“配置 secret 不等于路由已验签”。
- **验证状态**：与安全中间件、审批服务、渠道代码和相关测试核对；完成。

### DOC-010 渠道说明

- **实现思路**：按真实入口描述四渠道解析、回发、队列、fallback、白名单、限流、历史和 stub。
- **修改文件**：重写 `docs/CHANNELS.md`。
- **核心文档变更**：明确钉钉/飞书/QQ/Telegram 的凭据与真实回发条件；说明 webhook 全局鉴权冲突、未调用平台验签、QQ 默认 stub、重启后历史不可重试。
- **遇到的问题与解决方案**：`success=true` 可能只是 stub/ignored/denied。解决方式是要求同时检查 message、configured 和历史事件，不以 HTTP 成功断言真实送达。
- **验证状态**：与渠道类、manager、gateway 路由和测试核对；未宣称真实平台联调；完成。

### DOC-011 部署说明

- **实现思路**：从安装脚本、Dockerfile、Compose、nginx 和主应用反推本地与容器行为。
- **修改文件**：重写 `docs/DEPLOYMENT.md`。
- **核心文档变更**：区分 Vite、独立 nginx 和后端 `/ui`；说明当时的 MemorySaver、volume、单实例 JSON、生产安全前置和运维检查。
- **遇到的问题与解决方案**：本地 `npm run build` 不会自动生成根 `frontend_dist`。解决方式是明确本地 `/ui` 不能默认可用，而容器镜像会复制构建产物。
- **验证状态**：Compose 语法已验证；本轮未把 `docker compose up`、TLS 或生产 HA 标成已验证；完成。

### DOC-012 文档导航

- **实现思路**：提供首次阅读顺序、事实优先级、维护规则和归档说明。
- **修改文件**：重写 `docs/README.md`。
- **核心文档变更**：汇总全部现行专题；规定代码/OpenAPI/测试与文档冲突时的处理；禁止敏感信息和无证据的“生产就绪”表述。
- **遇到的问题与解决方案**：计划/进度仍需可访问但不能成为事实真源。解决方式是把二者归为计划/过程记录，并链接材料台账。
- **验证状态**：相对链接和现行文件名已人工核对；完成。

### DOC-013 项目落地计划书

- **实现思路**：删除旧 v3 中已完成阶段、伪代码和过期目标，只保留当前基线与真实未闭环工作。
- **修改文件**：完整重写 `docs/IMPLEMENTATION_PLAN.md`。
- **核心文档变更**：建立 PLAN-001—003 基线、PLAN-100—500 当前计划；每项包含阶段、优先级、依赖、步骤、验收与回滚。
- **遇到的问题与解决方案**：审批恢复、计划确认与 checkpoint 高度耦合。解决方式是先统一运行标识，再持久 checkpoint，随后分别闭环审批和多 Agent 计划。
- **验证状态**：与 REQ/FUN 状态及项目状态报告逐项对齐；未声称任何代码缺口已实现；完成。

### DOC-014 落实清单与实现记录

- **实现思路**：用短而可维护的现行清单替代 19 万字符历史流水账。
- **修改文件**：完整重写 `docs/PROGRESS.md`。
- **核心文档变更**：顶部增加可视化勾选清单；文档任务逐项 `[x]`，开发缺口按事实 `[ ]`/`[~]`；补充 Phase 40—46 摘要和本轮实现记录。
- **遇到的问题与解决方案**：旧记录曾得出“全量任务均完成”，与后续审计冲突。解决方式是保留历史摘要但显式纠偏，当前状态只服从代码审计。
- **验证状态**：清单与 IMPLEMENTATION_PLAN、PROJECT_STATUS_REPORT 一致；原长记录归档链接明确；完成。

### DOC-015 验收映射

- **实现思路**：以 REQ 为主线，将功能、API、页面、测试证据和后续 PLAN 串成可审查链路。
- **修改文件**：新建 `docs/ACCEPTANCE_CHECKLIST.md`。
- **核心文档变更**：建立状态定义、核心追踪矩阵、接口验收、页面验收和未闭环专项；流式、多 Agent 计划、工具审批、任务取消、领域 CRUD、前端测试均按事实标注。
- **遇到的问题与解决方案**：一个需求跨多个入口，单一完成态会掩盖差异。解决方式是拆分到可独立验收的层级条目，并给部分项绑定 PLAN。
- **验证状态**：当时完成了 REQ/FUN 映射，但“API 路径和页面路由已核对”的表述不准确；其中 `/chats`、登录页、monitor 全路径和 Agent 参数名等问题已在 DOC-017 重新按代码复核并纠偏。

### DOC-016 根 README 更新

- **实现思路**：保留快速开始，校正项目宣传口径并把新文档体系提升为入口。
- **修改文件**：更新根目录 `README.md`。
- **核心文档变更**：增加当前状态摘要和事实真源说明；更新文档索引；将能力表改为“状态+边界”表达。
- **遇到的问题与解决方案**：旧 README 容易让读者把规划/审批、任务取消和领域能力理解为完整闭环。解决方式是链接状态报告与验收清单，并明确运行时 OpenAPI/源码优先。
- **验证状态**：快速安装、后端/前端启动和 Docker 命令保留；文档链接已核对；完成。

### DOC-017 代码—文档一致性复核与纠偏

- **实现思路**：以 `frontend/src/App.tsx` 的 `parseRoute()`、条件渲染逻辑和 `ChatHistoryPanel`，以及 `backend/app/api/routes/` 的实际 Router 为事实源，逐项复核 REQ、FUN、API、PAGE、状态报告、架构与导航口径。
- **修改文件**：`docs/ACCEPTANCE_CHECKLIST.md`、`docs/REQUIREMENTS.md`、`docs/FEATURE_CATALOG.md`、`docs/DOCUMENT_INVENTORY.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/README.md`、`docs/ARCHITECTURE.md`、`docs/API.md`、`docs/CHANNELS.md`、`docs/SECURITY.md`、`docs/DEPLOYMENT.md`、`docs/TESTING.md`、`docs/PROGRESS.md`、根 `README.md`。
- **核心文档变更**：删除不存在的 `/chats` 深链宣称；将会话定位为 `/chat` 侧栏，将登录页定位为无独立路由的条件渲染；补全 monitor 路径和 `{agent_id}`；将 REQ-001/003/011/013/101/103/161 与 FUN-004/062/101 调整为部分实现；刷新材料台账、文档导航、架构直达路由和 2026-07-16 基线。
- **遇到的问题与解决方案**：DOC-015 曾写“页面路由已核对”，但验收表仍包含源码中不存在的路由。解决方式是不继承该结论，直接对照路由解析与后端装饰器，并在本记录中明确纠偏。
- **验证状态**：已确认 `/` 与 `/chat` 均进入聊天页；`/reports`、`/params`、`/las/import` 可直达但不在顶栏；会话与登录无独立路由；归档目录未修改。

### DOC-018 测试、构建及 Compose 复验

- **实现思路**：把 2026-07-16 已实际执行的后端回归、前端生产构建和 Compose 配置检查作为统一证据写入状态、验收、测试、台账、进度和入口文档。
- **修改文件**：`README.md`、`docs/ACCEPTANCE_CHECKLIST.md`、`docs/DOCUMENT_INVENTORY.md`、`docs/PROJECT_STATUS_REPORT.md`、`docs/TESTING.md`、`docs/PROGRESS.md`。
- **核心文档变更**：当时将后端回归、前端构建与 Compose 证据写入入口文档；该项完成时基线约为 `166 passed`。现行最近基线已由 PLAN-400/410/420/500/600—650 更新为 pytest `206` / Vitest `25` / E2E `8`。
- **遇到的问题与解决方案**：现行材料曾存在多个旧测试总数和耗时。解决方式是统一采用最近一次实际输出，同时保留“构建/语法通过不等于 E2E、外部联通或生产就绪”的边界。
- **验证状态**：该项完成当时后端约 `166 passed`，前端 `npm run build` 与 `docker compose config --quiet` 通过；现行数字以顶部清单与 `TESTING.md` 为准。

## 四、后续记录规则

1. 完成 PLAN 项时，在本文件顶部清单更新状态，并在本节前追加实现记录。
2. 记录必须包含实现思路、修改文件、核心变更、问题与解决方案、验证状态。
3. 只有代码、测试、OpenAPI 和端到端证据同时满足计划验收标准，才能标记 `[x]`。
4. fake/mock 证据必须明确标注；真实 Provider、渠道和生产环境未验证时不得外推。
5. 不再把完整代码片段和每次小修复长期堆入本文件；详细历史由版本控制和归档承载。
