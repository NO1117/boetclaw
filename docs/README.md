# BoetClaw 文档导航

> 文档基线：2026-07-20。

本目录记录当前实现、使用边界和历史过程。阅读时应先区分“现行说明”和“计划/进度记录”；
文档描述与代码冲突时，以可运行事实为准。

当前文档状态：PLAN-100—420 已完成；PLAN-500 文档治理与 PLAN-600—710 运维闭环（含文档/验收同步）已完成。领域单实例 CRUD、运维持久/验签/插件与 Agent 治理、前端关键组件/协议测试、Playwright Chromium E2E（fake Provider）与 CI workflow 已验收，但不承诺跨资源 exactly-once、多实例恢复、跨进程取消、真实 Provider/渠道联通或数据库事务。2026-07-20 本机基线：后端 pytest `213 passed`、Vitest `5 files / 29 passed`、E2E `8 passed`（fake Provider）；ruff/mypy/OpenAPI/coverage/build/compose 均通过；**Git 已初始化，推送到 GitHub 后启用 Actions / required checks**（目标仓库 `NO1117/boetclaw`）。

## 现行文档

- [项目需求](REQUIREMENTS.md)：按当前代码整理的需求、范围、状态和验收口径。
- [功能清单](FEATURE_CATALOG.md)：功能编号、实现路径、状态、缺口及需求映射。
- [项目状态报告](PROJECT_STATUS_REPORT.md)：截至 2026-07-20 的验证结果、闭环程度和主要风险。
- [验收清单](ACCEPTANCE_CHECKLIST.md)：REQ—FUN—API—PAGE—TEST—PLAN 的可追溯验收映射。
- [材料台账](DOCUMENT_INVENTORY.md)：现行/归档文档及代码事实来源的盘点和处置规则。
- [实施计划](IMPLEMENTATION_PLAN.md)：当前有效的 `PLAN-*` 工作、依赖、步骤和验收标准。
- [落实进度](PROGRESS.md)：当前清单、文档工作和实现记录。
- [架构说明](ARCHITECTURE.md)：后端、前端、Agent、存储和主要运行链路。
- [API 说明](API.md)：当前 HTTP API 的用途与调用方式；精确 schema 仍以运行时 OpenAPI 为准。
- [安全说明](SECURITY.md)：ToolGuard、Plan Gate、鉴权、限流、渠道和扩展安全边界。
- [渠道说明](CHANNELS.md)：钉钉、飞书、QQ、Telegram、队列、白名单、历史与 stub。
- [部署说明](DEPLOYMENT.md)：本地、Docker、nginx、`/ui`、持久化和生产检查。
- [测试说明](TESTING.md)：后端测试矩阵、命令、当前缺口和建议验收用例。
- [首版发布说明](RELEASE.md)：v0.1.0 公开仓库发布范围与已知限制。

建议首次部署按以下顺序阅读：

1. `PROJECT_STATUS_REPORT.md`
2. `REQUIREMENTS.md`、`FEATURE_CATALOG.md`
3. `ACCEPTANCE_CHECKLIST.md`
4. `ARCHITECTURE.md`、`API.md`
5. `DEPLOYMENT.md`、`SECURITY.md`、`TESTING.md`
6. `IMPLEMENTATION_PLAN.md`、`PROGRESS.md`
7. 按需查阅 `CHANNELS.md` 和 `DOCUMENT_INVENTORY.md`

## 事实优先级

发生不一致时，按以下顺序判断：

1. 当前分支的可执行代码、配置模型、Docker/nginx/安装脚本。
2. 当前分支测试的实际收集与运行结果。
3. 运行中服务生成的 `/openapi.json`、健康状态和可复现实验结果。
4. 本目录的现行文档。
5. `PROGRESS.md`、`IMPLEMENTATION_PLAN.md`、提交说明和其他历史性文字。

示例配置只说明字段和默认行为，不证明生产安全。测试通过只证明已执行场景，不证明真实 LLM、
消息平台、网络、代理或多副本部署已经验证。

## 维护规则

- 代码变更如果改变 API、环境变量、持久化路径、安全边界、渠道行为、部署步骤或测试基线，
  应在同一变更中更新对应文档。
- 路径从仓库根目录书写，例如 `backend/app/main.py`；命令必须注明执行目录或平台差异。
- 数量、版本、测试结果和支持状态应附事实来源或日期，避免使用“完整”“安全”“生产就绪”等
  无法由当前证据支持的表述。
- 明确区分“已实现”“默认启用”“需要配置”“stub”“建议”和“尚未覆盖”。
- 不在文档中写入真实 token、密码、Cookie、用户标识、内部域名或 workspace 业务数据。
- 修改文档前至少核对相关实现和测试；涉及部署时还要核对 `Dockerfile`、
  `docker-compose.yml`、`deploy/nginx.conf` 和安装脚本。
- 测试矩阵发生变化时，同时更新 `TESTING.md` 的文件数、静态用例数、实际收集数和最近验证结果。
- 新增现行文档时更新本导航；相对链接应在仓库浏览器和本地 Markdown 预览中都可用。

## 归档说明

- [开发进度](PROGRESS.md) 和 [实施计划](IMPLEMENTATION_PLAN.md) 记录阶段目标、完成情况和过程决策，
  具有归档性质，不应单独作为当前功能、安全性或部署行为的依据。
- `archive/2026-07-15/` 保存专题文档整理前的 `*_legacy.md` 快照，以及完整计划/进度历史；
  这些文件只用于追溯，不再与现行文档双向维护。
- 归档文件的具体状态和处置以 [材料台账](DOCUMENT_INVENTORY.md) 为准。
- 历史记录原则上保留原始时间语境。如其内容持续维护为现行说明，应拆分或合并到上方对应主题，
  而不是在历史段落中静默改写过去结论。
- 已移除功能的详细说明如仍有追溯价值，应标注适用版本/日期并移入明确的归档位置；否则删除失效说明，
  避免与现行文档并列造成误导。
