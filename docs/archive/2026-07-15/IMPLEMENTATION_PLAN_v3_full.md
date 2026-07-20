# BoetClaw 详尽落地实施方案（v3·实现基线与闭环补强）

> 参考基准：[QwenPaw](https://qwenpaw.agentscope.io/docs/intro)（AgentScope 团队）
> 核心框架：[LangChain DeepAgents](https://docs.langchain.com/oss/python/deepagents/overview) `deepagents==0.6.12` / `langgraph==1.2.8` / `langchain==1.3.11`
> 本文档为**实现基线 + 后续闭环行动指南**：既保留已落地阶段的技术方案，也基于 2026-07-14 代码库功能审计结果修正目标、进度、路由与补强步骤。
> 所有 DeepAgents API 均已在本机 `.venv` 实测核实（见 A.2）。

> **2026-07-14 审计口径**：当前前端没有 `react-router` 式客户端路由表，实际为单页 React 控制台；页面能力由主聊天区、右侧任务/追踪/审批侧栏、管理控制台 Tab 承载。后端业务路由集中在 `/api/v1/*`。审计识别出 9 个核心业务模块、5 个完整接通模块、9 个部分接通模块、12 类建议补齐缺口。本文后续所有阶段状态均按“代码/API 已实现”和“产品/页面闭环已完成”两个口径区分。

---

# Part A. 背景与基准分析

## A.1 QwenPaw 能力与六层架构（剖析结论）

QwenPaw 是本地优先、多端触达、技能驱动、多智能体协作的个人 AI 助理。六层架构：

```
Channels(18渠道) → Console(Vue3/Tauri) → Agent(ReActAgent+Mixins)
→ Security(ToolGuard+SkillScanner) → Provider(ABC+8实现) → Memory/Context(3后端)
```

需移植到 DeepAgents 的 8 个关键机制：

| # | QwenPaw 机制 | 本项目落地方式 |
|---|-------------|---------------|
| 1 | MRO 链式 Mixin（`_acting` 叠加） | DeepAgents **Middleware 栈**（`wrap_tool_call`/`before_model`） |
| 2 | Plan 门控（`/plan`→确认→执行） | `write_todos` + `PlanGateMiddleware` + LangGraph `interrupt` |
| 3 | 工具三层注册 | `ToolRegistry`（硬编码/插件`__all__`/异步任务） |
| 4 | ToolGuard 4 级 + 3 Guardian | `ToolGuardMiddleware.wrap_tool_call` + Guardian 引擎 |
| 5 | 技能池 + 工作区技能 | `SkillPoolService` + `SkillService` + `skills=` |
| 6 | Memory 3 后端 | `memory=`（AGENTS.md）+ `StoreBackend` + 可选向量 |
| 7 | 多 Agent Workspace | `MultiAgentManager` + 独立 `FilesystemBackend`/checkpointer |
| 8 | 两阶段启动 | FastAPI lifespan Phase1(<100ms)/Phase2(后台 task) |

## A.2 DeepAgents 0.6.12 已验证 API 事实（落地基石）

> 以下均通过 `.venv\Scripts\python` 实测，代码骨架据此编写，可直接运行。

**A.2.1 `create_deep_agent` 关键参数**（实测签名）：

```python
create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    permissions: list[FilesystemPermission] | None = None,
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol] | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    response_format=None, state_schema=None, context_schema=None,
    checkpointer: None | bool | BaseCheckpointSaver = None,
    store: BaseStore | None = None,
    debug: bool = False, name: str | None = None, cache=None,
) -> CompiledStateGraph
```

**A.2.2 `AgentMiddleware` 可用钩子**（实测）：
`before_agent` / `after_agent` / `before_model` / `after_model` / `wrap_model_call` / `wrap_tool_call`（均有 `a*` 异步版）、`name`、`state_schema`。

- `before_model(self, state, runtime) -> dict[str, Any] | None`
- `wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]) -> ToolMessage | Command`
  → **这是实现 ToolGuard 拦截的关键钩子**。

**A.2.3 `SubAgent` TypedDict 字段**（实测）：
`name, description, system_prompt`（必填）；`tools, model, middleware, interrupt_on, skills, permissions, response_format`（NotRequired）。

**A.2.4 `InterruptOnConfig` 字段**（实测）：
`allowed_decisions: list[DecisionType]`、`description`、`args_schema`、`when: Callable[[ToolCallRequest], bool]`。
`DecisionType` = `"approve" | "edit" | "reject"`（HITL 决策）。

**A.2.5 可用 Backend**（实测 `deepagents.backends`）：
`StateBackend`（默认，state 内存）、`FilesystemBackend`（本地磁盘）、`StoreBackend`（LangGraph Store）、`CompositeBackend`（路由）、`LocalShellBackend`（含 execute）、`LangSmithSandbox`。
→ **多 Workspace 隔离用 `FilesystemBackend(root=workspace_dir)`**。

**A.2.6 内置中间件**（实测 `deepagents.middleware`）：
`FilesystemMiddleware`、`SubAgentMiddleware`、`SkillsMiddleware`、`MemoryMiddleware`、`SummarizationMiddleware`、`RubricMiddleware` 等。

## A.3 现有 boetclaw 实现基线评估（2026-07-14）

| 模块 | 代码/API 状态 | 产品/页面闭环状态 | 后续动作 |
|------|---------------|------------------|----------|
| FastAPI + lifespan | ✅ 两阶段启动、API Token 鉴权与内存限流已实现 | ✅ `/monitor/health` 可查 ready/agent_ready 且不受鉴权影响 | 保持 API 安全回归测试 |
| Agent 核心 | ✅ 工厂、中间件、DeepAgents 运行时已实现 | ✅ 聊天主工作台与会话历史可用 | Phase 15/16 继续补扩展治理与业务闭环 |
| Plan 门控 | ✅ `/plan`、interrupt、confirm/edit API、计划历史审计已实现 | ✅ ChatPanel 内嵌 PlanConfirm，支持批准/拒绝/编辑计划 | 保持计划确认回归测试 |
| ToolGuard 安全 | ✅ 引擎、Guardian、审批 API、审批历史持久化已实现 | ✅ 安全配置页、待审批、审批历史已接入 | 保持审计持久化回归测试 |
| 技能体系 | ✅ 池/工作区/扫描/启停 API 已实现 | ⚠️ 可列表、添加、启停、扫描；缺安装/编辑/删除详情页 | Phase 14/15 补技能治理 |
| 多 Agent Workspace | ✅ list/create/get/delete、files/history API 与懒加载已实现 | ✅ `/agents/:agentId` 详情、删除、技能聚合、运行历史、文件索引已接入 | Agent 产物关联与筛选已补齐 |
| Provider | ✅ OpenAI/Anthropic/Ollama + base_url 支持，配置可持久化到 `.env` | ✅ 可检测、列模型、写入配置、切换默认模型 | 保持 Provider 写入回归测试 |
| 渠道网关 | ✅ 钉钉/飞书/QQ/Telegram Webhook 与队列 | ⚠️ 无渠道配置、队列、消息审计页面 | Phase 15 补渠道运维 |
| 定时/心跳 | ✅ Cron/Heartbeat API 与 APScheduler | ⚠️ 可建删 Cron/开关心跳；缺编辑、启停、运行历史 | Phase 14/15 补调度闭环 |
| 插件/命令 | ✅ 插件安全默认加载、命令注册 | ⚠️ 插件页只读+reload；缺启停/安装/详情 | Phase 15 补插件治理 |
| 可观测性 | ✅ trace、timeline、OTel、JSONL，时间线含耗时/间隔/分类详情 | ✅ `/trace/:traceId` 深链与结构化时间线详情页已接入 | 保持可观测性回归测试 |
| 文件产物 | ✅ 图表/代码文件接口与侧车元数据自动写入 | ✅ 产物中心、预览、下载、任务/Trace/Agent/井号关联已接入 | 保持生成链路回归测试 |
| 领域业务数据 | ⚠️ 内置模拟 `query_drilling_params` | ❌ 无井/日报/LAS/参数库实体页面 | Phase 16 补领域数据闭环 |

---

# Part B. 目标与总体架构

## B.1 项目目标（可度量，含当前状态）

| ID | 目标 | 当前状态 | 下一步闭环指标 |
|----|------|----------|----------------|
| G1 | 自主规划+执行闭环 | ✅ 已实现 `/plan`→todos→interrupt→confirm | 增加 edit 计划、计划历史和失败恢复记录 |
| G2 | 技能双层体系 | ⚠️ 池/工作区解析、添加、启停、扫描已实现 | 补技能安装、详情、编辑、删除、扫描详情页 |
| G3 | 多智能体隔离 | ⚠️ 工作区隔离、懒加载和 API 已实现 | 补 Agent 详情、删除、运行/文件/技能聚合页 |
| G4 | 多网关接入 | ⚠️ 4 渠道 Webhook→任务→回复已实现 | 补渠道配置、队列深度、消息历史、失败重试 |
| G5 | 高可用后端 | ✅ API、SSE、两阶段启动、静态 `/ui/`、API 鉴权与限流已实现 | 保持 API 安全与健康检查回归 |
| G6 | 可观测性 | ⚠️ 事件、统计、timeline、JSONL 已实现 | 补独立 Trace 页面、深链、运行详情页 |
| G7 | 安全防护 | ⚠️ Guard/审批 API 已实现 | 补安全配置页、审批历史、线程关联修正 |
| G8 | 定时能力 | ⚠️ Cron/心跳可用 | 补任务编辑、启停、运行历史与渠道回发状态 |
| G9 | Web 控制台 | ⚠️ 单页控制台覆盖主要能力 | 引入页面级路由和产品闭环页 |
| G10 | 钻井领域闭环 | ❌ 仅模拟参数与工具模板 | 补井、井段、日报、LAS、参数库 CRUD 与导入 |

## B.2 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│ Channels Gateway  钉钉│飞书│QQ│Telegram│Discord│OneBot        │  M8
│   BaseChannel(ABC) + ChannelManager(队列) + MessageRenderer   │
├─────────────────────────────────────────────────────────────┤
│ React Console  ──HTTP/SSE──▶  FastAPI(REST+SSE)  ◀── Webhook  │  M12/M10
├─────────────────────────────────────────────────────────────┤
│ MultiAgentManager  route(4级) → Workspace(懒加载)             │  M7
│   Workspace{ config, FilesystemBackend, checkpointer, agent } │
├─────────────────────────────────────────────────────────────┤
│ BoetClawAgentFactory.build() → create_deep_agent(             │  M1
│   model, tools=ToolRegistry.resolve(), subagents,             │
│   skills=SkillService.effective(), memory,                    │
│   middleware=[ Observability, PlanGate, ToolGuard ],          │
│   interrupt_on, permissions, backend, checkpointer )          │
├─────────────────────────────────────────────────────────────┤
│ Middleware:  ObservabilityMW → PlanGateMW → ToolGuardMW       │  M11/M1/M4
│              (before_model / wrap_tool_call / after_model)    │
├─────────────────────────────────────────────────────────────┤
│ ToolRegistry(M3) │ SkillSystem(M2) │ Memory(M6) │ Provider(M5)│
│ MCPManager(三段恢复) │ SecurityEngine(M4) │ Scheduler(M9)     │
│ PluginLoader(M13) │ CommandRegistry(魔法命令)                 │
└─────────────────────────────────────────────────────────────┘
```

## B.3 模块清单

M1 Agent核心 / M2 技能体系 / M3 工具&MCP / M4 安全 / M5 Provider / M6 记忆上下文 /
M7 多智能体 / M8 渠道网关 / M9 调度 / M10 API / M11 可观测 / M12 控制台 / M13 插件

## B.4 当前页面与路由边界

- **前端页面入口**：开发态通常为 `/`，生产内置前端为 `/ui/`。当前没有独立客户端路由，所有页面能力均由 `App.tsx` 内部状态、右侧栏和 `ConsoleModal` Tab 切换完成。
- **主要前端区域**：`ChatPanel`（智能对话/计划确认）、`TaskMonitor`（任务列表/创建/详情遮罩）、`SidePanel`（追踪/工具/监控）、`ApprovalCard`（待审批）、`AgentSwitcher`（Agent 切换/创建）、`ConsoleModal`（技能/模型/定时心跳/插件）。
- **主要后端路由**：`/api/v1/agent/*`、`/tasks/*`、`/monitor/*`、`/security/*`、`/skills/*`、`/agents/*`、`/providers/*`、`/plugins`、`/commands`、`/tools/*`、`/files/*`、`/gateway/*`。
- **闭环缺口**：任务重跑/取消 UI、安全配置、Agent 详情、Provider 配置写入、技能安装编辑、插件启停、MCP 管理、渠道审计、产物中心、会话历史、钻井领域实体均需作为后续产品化阶段补齐。

## B.5 目标目录结构（完整文件树）

```
boetclaw/
├── backend/
│   ├── app/
│   │   ├── main.py                         # 两阶段 lifespan
│   │   ├── core/
│   │   │   ├── config.py                    # 已有，扩展
│   │   │   ├── observability.py             # 已有，扩展
│   │   │   ├── agent_factory.py             # ★M1 BoetClawAgentFactory
│   │   │   └── startup.py                   # ★两阶段启动编排
│   │   ├── middleware/                       # ★M1/M4/M11
│   │   │   ├── observability_mw.py
│   │   │   ├── plan_gate_mw.py
│   │   │   └── tool_guard_mw.py
│   │   ├── agents/                           # ★M7
│   │   │   ├── workspace.py
│   │   │   ├── multi_agent_manager.py
│   │   │   ├── agent_context.py              # 4 级路由
│   │   │   └── subagents.py                  # 子智能体定义
│   │   ├── skills_system/                    # ★M2
│   │   │   ├── models.py
│   │   │   ├── store.py
│   │   │   ├── pool_service.py
│   │   │   ├── workspace_service.py
│   │   │   ├── registry.py
│   │   │   └── scanner.py
│   │   ├── security/                         # ★M4
│   │   │   ├── models.py
│   │   │   ├── execution_level.py
│   │   │   ├── engine.py
│   │   │   ├── approval.py
│   │   │   └── guardians/
│   │   │       ├── base.py
│   │   │       ├── rule_guardian.py
│   │   │       ├── file_guardian.py
│   │   │       └── shell_guardian.py
│   │   ├── providers/                        # ★M5
│   │   │   ├── base.py
│   │   │   ├── manager.py
│   │   │   ├── openai_provider.py
│   │   │   ├── anthropic_provider.py
│   │   │   ├── ollama_provider.py
│   │   │   └── capability_cache.py
│   │   ├── memory/                           # ★M6
│   │   │   └── context_policy.py
│   │   ├── tools/                            # M3
│   │   │   ├── builtin.py                    # 已有
│   │   │   ├── registry.py                   # ★三层注册
│   │   │   └── mcp_manager.py                # 已有，加三段恢复
│   │   ├── services/
│   │   │   ├── task_scheduler.py             # 已有 → APScheduler 化
│   │   │   ├── heartbeat.py                  # ★M9
│   │   │   └── gateway/
│   │   │       ├── base.py                   # ★BaseChannel
│   │   │       ├── manager.py                # ★ChannelManager
│   │   │       ├── router.py                 # 已有 → 重构
│   │   │       ├── renderer.py               # ★渲染
│   │   │       └── channels/
│   │   │           ├── dingtalk.py
│   │   │           ├── feishu.py
│   │   │           ├── qq.py
│   │   │           ├── telegram.py
│   │   │           └── discord.py
│   │   ├── plugins/                          # ★M13
│   │   │   ├── architecture.py               # PluginType
│   │   │   ├── loader.py
│   │   │   └── registry.py
│   │   ├── commands/                         # ★魔法命令
│   │   │   └── registry.py
│   │   └── api/
│   │       ├── schemas.py                    # 已有，扩展
│   │       └── routes/
│   │           ├── agent.py agents.py tasks.py tools.py
│   │           ├── skills.py security.py providers.py
│   │           ├── gateway.py monitor.py files.py commands.py
│   ├── skills/                               # 内置技能包
│   ├── tests/                                # ★pytest
│   ├── AGENTS.md  .env.example  requirements.txt  run.py
├── frontend/  (React，扩展管理页)
├── docs/IMPLEMENTATION_PLAN.md               # 本文档
├── docker-compose.yml  Dockerfile  README.md
```

---

# Part C. 通用规范（横切，所有阶段遵守）

## C.1 依赖版本锁定

后端在现有 `requirements.txt` 基础上新增：

```
apscheduler>=3.11,<4        # 已在
python-telegram-bot>=21.0   # Phase 8（Telegram）
discord.py>=2.4             # Phase 8（Discord，可选）
pytest>=8.3                 # 测试
pytest-asyncio>=0.24
```

## C.2 环境变量清单（新增，追加到 `.env.example`）

```
# 安全
TOOL_GUARD_ENABLED=true
TOOL_GUARD_LEVEL=smart          # strict|smart|auto|off
TOOL_GUARD_DENIED_TOOLS=        # 逗号分隔
FILE_GUARD_DENY_DIRS=.env,.git,~/.ssh

# 多智能体
DEFAULT_AGENT_ID=default
AGENTS_ROOT=./workspace/agents  # 每 agent 一个子目录

# 定时/心跳
HEARTBEAT_ENABLED=false
HEARTBEAT_INTERVAL_MINUTES=120
HEARTBEAT_PROMPT=汇总我的待办

# Provider 本地模型
OLLAMA_BASE_URL=http://localhost:11434
```

## C.3 核心数据模型（pydantic，`app/api/schemas.py` + 各模块 models）

见附录 附1（完整字段表）。关键：`AgentConfig`、`WorkspaceInfo`、`SkillInfo`、`ApprovalRequest`、`GuardResult`、`CronJob`。

## C.4 API 契约总表

见附录 附2（method/path/请求/响应/状态码）。

## C.5 事件与追踪规范

- 所有事件统一经 `emit_event(EventType, data, trace_id, run_id)`。
- 新增 `EventType`：`PLAN_CREATED`、`PLAN_CONFIRMED`、`GUARD_BLOCK`、`GUARD_APPROVED`、`APPROVAL_REQUESTED`、`SKILL_LOADED`、`CRON_TRIGGER`、`HEARTBEAT`。
- Trace 贯通规则：渠道消息 → 生成 `trace_id` → 注入 `ContextVar` → API/Agent/工具/子智能体全程复用。

## C.6 编码规范

- Python 3.11-3.13（LangChain/Pydantic 当前不建议 Python 3.14+），全量类型注解，`from __future__ import annotations`。
- 中间件命名唯一（`name` 属性），顺序敏感：Observability→PlanGate→ToolGuard。
- 禁止在中间件 `__init__` 做 IO；懒初始化重资源。

## C.7 测试策略

- 每阶段附 `tests/test_phaseN_*.py`，用 `pytest`。
- 关键单测：Guardian 规则、Plan 门控状态、路由优先级、技能解析、渠道解析。
- 冒烟测试：`python -c "from app.main import app"` 必须始终通过。

---

# Part D. 分阶段实施（逐步可操作）

> 每阶段结构固定：**目标 / 前置 / 步骤(文件+动作+代码+验证+验收) / 交付物 / DoD**。
> 阶段间依赖：0→1→2→3 为关键路径；4-13 在 3 完成后可并行分组。

---

## Phase 0 · 项目校准（0.5 天）

**目标**：建立测试骨架、扩展配置与事件类型、锁定依赖，确保后续阶段有验证手段。

**步骤**

- **Step 0.1** 编辑 `backend/requirements.txt`，加入 C.1 依赖；执行安装。
  - 验证：`.venv\Scripts\pip install -r requirements.txt`
- **Step 0.2** 编辑 `backend/.env.example`，追加 C.2 变量；`config.py` 增加对应字段（`tool_guard_enabled` 等）。
  - 验收：`python -c "from app.core.config import settings; print(settings.tool_guard_level)"` 输出 `smart`。
- **Step 0.3** 扩展 `observability.py` 的 `EventType` 枚举（C.5 新增项）。
- **Step 0.4** 新建 `backend/tests/__init__.py` 与 `tests/test_smoke.py`：

```python
def test_import_app():
    from app.main import app
    assert app.title == "BoetClaw DeepAgents"
```
  - 验证：`.venv\Scripts\python -m pytest -q`

**DoD**：pytest 通过；config 新字段可读；依赖安装成功。

---

## Phase 1 · 核心基座：Agent 工厂 + 中间件骨架 + 两阶段启动（2 天）

**目标**：把现有单 Agent 重构为 `BoetClawAgentFactory`，接入可观测性中间件，改造为两阶段启动。

**前置**：Phase 0 完成。

**步骤**

- **Step 1.1** 新建 `app/middleware/observability_mw.py` — 链路追踪中间件（基于实测钩子）：

```python
from __future__ import annotations
from typing import Any, Callable
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.core.observability import EventType, emit_event

class ObservabilityMiddleware(AgentMiddleware):
    name = "boetclaw_observability"

    def before_model(self, state, runtime) -> dict[str, Any] | None:
        msgs = state.get("messages", [])
        emit_event(EventType.THINKING, {"phase": "before_model", "msg_count": len(msgs)})
        return None

    def after_model(self, state, runtime) -> dict[str, Any] | None:
        msgs = state.get("messages", [])
        last = msgs[-1] if msgs else None
        tool_calls = getattr(last, "tool_calls", None) or []
        if tool_calls:
            for tc in tool_calls:
                emit_event(EventType.TOOL_CALL, {"tool": tc.get("name"), "args": str(tc.get("args"))[:500]})
        return None

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable) -> ToolMessage | Command:
        name = request.tool_call.get("name", "?")
        emit_event(EventType.TOOL_CALL, {"tool": name, "stage": "invoke"})
        result = handler(request)
        emit_event(EventType.TOOL_RESULT, {"tool": name, "stage": "done"})
        return result
```
  - 验证：`python -c "from app.middleware.observability_mw import ObservabilityMiddleware as M; print(M.name)"`

- **Step 1.2** 新建 `app/core/agent_factory.py` — 集中构建 Agent：

```python
from __future__ import annotations
from typing import Any
from deepagents import create_deep_agent
from app.core.config import settings
from app.tools.builtin import get_builtin_tools
from app.tools.mcp_manager import mcp_manager
from app.middleware.observability_mw import ObservabilityMiddleware

DEFAULT_INTERRUPT = {"write_file": True, "edit_file": True, "delete": True}

class BoetClawAgentFactory:
    @staticmethod
    def build(*, model=None, tools=None, subagents=None, skills=None,
              memory=None, backend=None, checkpointer=None,
              extra_middleware: list | None = None) -> Any:
        mw = [ObservabilityMiddleware()] + (extra_middleware or [])
        return create_deep_agent(
            model=model or settings.model_string,
            tools=(tools if tools is not None else get_builtin_tools()) + mcp_manager.tools,
            subagents=subagents,
            skills=skills, memory=memory,
            middleware=mw,
            interrupt_on=DEFAULT_INTERRUPT,
            backend=backend, checkpointer=checkpointer,
            system_prompt=SYSTEM_PROMPT,
        )
```
  （`SYSTEM_PROMPT` 从现有 `agent.py` 迁移。）

- **Step 1.3** 改造 `app/core/agent.py` 的 `AgentManager.initialize()` 调用工厂；保留 `invoke`/`stream`/`list_tools` 对外接口不变（向后兼容 Phase<5 的 API）。
  - 验收：现有 `/api/v1/agent/tools` 仍返回工具列表。

- **Step 1.4** 新建 `app/core/startup.py` — 两阶段启动编排：

```python
from __future__ import annotations
import asyncio, time
from app.core.observability import get_logger
logger = get_logger("startup")

async def phase1_fast(app) -> None:
    t = time.perf_counter()
    # 仅实例化核心 manager（不做网络 IO）
    from app.agents.multi_agent_manager import multi_agent_manager  # Phase5 引入，先容错
    app.state.ready = True
    logger.info("phase1_done", elapsed_ms=(time.perf_counter()-t)*1000)

async def phase2_background(app) -> None:
    from app.tools.mcp_manager import mcp_manager
    from app.core.agent import agent_manager
    await mcp_manager.connect()
    await agent_manager.initialize()
    app.state.agent_ready = True
    logger.info("phase2_done")
```

- **Step 1.5** 改造 `app/main.py` 的 `lifespan`：Phase1 同步跑完 → `asyncio.create_task(phase2_background(app))` 后台跑；`/monitor/health` 返回 `agent_ready` 标志。
  - 验证：启动后立即 `GET /api/v1/monitor/health` 返回 `{"status":"healthy","agent_ready":false}`，数秒后变 `true`。

**交付物**：可观测性中间件、Agent 工厂、两阶段启动。
**DoD**：`pytest` 通过；服务秒级就绪；每次 chat 产生 before_model/tool_call/tool_result 事件（`GET /monitor/events` 可见）。

---

## Phase 2 · Plan 门控 + HITL 确认流（2 天）

**目标**：实现"进入规划态 → 生成计划 → interrupt 等待用户确认 → 确认后执行"闭环。

**前置**：Phase 1。

**设计**：用 DeepAgents 内置 `write_todos` 作为规划工具；`PlanGateMiddleware` 维护 `plan_phase` 状态；用 LangGraph `interrupt()` 暂停等待前端 resume。

**步骤**

- **Step 2.1** 扩展状态：新建 `state_schema` 继承 `DeepAgentState`，增加字段 `plan_phase: str`（`idle|planning|awaiting_confirm|executing`）。

```python
from deepagents import DeepAgentState
class BoetClawState(DeepAgentState):
    plan_phase: str
```

- **Step 2.2** 新建 `app/middleware/plan_gate_mw.py`：

```python
from __future__ import annotations
from typing import Any, Callable
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langgraph.types import interrupt, Command
from langchain_core.messages import ToolMessage
from app.core.observability import EventType, emit_event

PLAN_TOOLS = {"write_todos"}

class PlanGateMiddleware(AgentMiddleware):
    name = "boetclaw_plan_gate"

    def before_model(self, state, runtime) -> dict[str, Any] | None:
        phase = state.get("plan_phase", "idle")
        # 若处于 awaiting_confirm，注入系统提示要求仅修订/确认计划
        return None

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable) -> ToolMessage | Command:
        tool = request.tool_call.get("name", "")
        phase = request.state.get("plan_phase", "idle") if hasattr(request, "state") else "idle"
        # 规划态下拦截非规划工具
        if phase == "planning" and tool not in PLAN_TOOLS:
            return ToolMessage(
                content="当前处于规划阶段，请先用 write_todos 制定完整计划。",
                tool_call_id=request.tool_call["id"], status="error")
        # 计划生成后（write_todos 执行）→ 触发确认 interrupt
        if tool == "write_todos" and phase in ("planning", "idle"):
            result = handler(request)
            emit_event(EventType.PLAN_CREATED, {"tool": tool})
            decision = interrupt({"type": "plan_confirm",
                                  "todos": request.tool_call.get("args", {})})
            emit_event(EventType.PLAN_CONFIRMED, {"decision": decision})
            return result
        return handler(request)
```
  > 注：`interrupt()` 会挂起图，等待通过 `Command(resume=...)` 恢复；实际字段名以运行期 `request` 属性为准，Step 2.5 联调校正。

- **Step 2.3** 工厂支持注入 `PlanGateMiddleware` 与 `state_schema=BoetClawState`（新增 `enable_plan_gate` 开关）。

- **Step 2.4** 新增 API `POST /api/v1/agent/plan/confirm`（body: `{thread_id, decision: "approve"|"reject"|"edit", edited_todos?}`）→ 用 `agent.ainvoke(Command(resume=decision), config)` 恢复图。

```python
from langgraph.types import Command
@router.post("/plan/confirm")
async def plan_confirm(req: PlanConfirmRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    result = await agent_manager.agent.ainvoke(Command(resume=req.decision), config=config)
    return {"resumed": True, "response": _extract(result)}
```

- **Step 2.5** 联调：用 checkpointer（已有 MemorySaver），走 `/plan` 触发（Step 2.6 命令），验证 interrupt→confirm 恢复。

- **Step 2.6** 魔法命令占位：请求消息以 `/plan ` 开头时，服务端将 `plan_phase` 预置为 `planning`（Phase 10 完善命令系统，这里先在 chat 路由做前缀识别）。

**验证**
```
POST /agent/chat {"message":"/plan 帮我生成XX-1井完井报告并画图"}
→ 返回 interrupt 标记；GET /monitor/events 见 PLAN_CREATED
POST /agent/plan/confirm {"thread_id":"...","decision":"approve"}
→ 继续执行，见后续 tool_call
```

**交付物**：Plan 状态、门控中间件、确认 API。
**DoD**：规划→确认→执行三段可复现；拒绝（reject）时不执行后续工具。

---

## Phase 3 · ToolGuard 安全层（2.5 天）

**目标**：工具执行前经安全引擎评估，按 4 级策略放行/拦截/审批；实现 3 个 Guardian。

**前置**：Phase 1（中间件机制）、Phase 2（interrupt/审批复用）。

**步骤**

- **Step 3.1** `app/security/execution_level.py`：

```python
from enum import Enum
class ToolExecutionLevel(str, Enum):
    STRICT="strict"; SMART="smart"; AUTO="auto"; OFF="off"
class GuardSeverity(str, Enum):
    INFO="info"; LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"
```

- **Step 3.2** `app/security/models.py`：`GuardFinding{severity, category, message, guardian}`、`GuardResult{allowed: bool, requires_approval: bool, findings: list, reason: str}`。

- **Step 3.3** `app/security/guardians/base.py`：

```python
from abc import ABC, abstractmethod
class BaseGuardian(ABC):
    name: str
    @abstractmethod
    def inspect(self, tool_name: str, args: dict) -> "GuardResult": ...
```

- **Step 3.4** 三个 Guardian（各含默认规则）：
  - `rule_guardian.py`：读 `TOOL_GUARD_DENIED_TOOLS` + 内置高危工具集（`execute_shell_command`,`delete`,`write_file`,`edit_file`）→ MEDIUM/HIGH。
  - `file_guardian.py`：检查路径参数命中 `FILE_GUARD_DENY_DIRS`（`.env`,`.git`,`~/.ssh` 等）→ CRITICAL 拒绝。
  - `shell_guardian.py`：正则检测 shell 混淆（`base64 -d | sh`、`;rm -rf`、反引号嵌套、`curl|sh`）→ HIGH。

```python
# rule_guardian.py 关键逻辑
HIGH_RISK = {"execute_shell_command","delete"}
MED_RISK  = {"write_file","edit_file"}
def inspect(self, tool_name, args):
    if tool_name in self._denied: return GuardResult(allowed=False, reason="denied by config")
    if tool_name in HIGH_RISK: return GuardResult(allowed=True, requires_approval=True, findings=[GuardFinding(HIGH,...)])
    if tool_name in MED_RISK:  return GuardResult(allowed=True, requires_approval=True, findings=[GuardFinding(MEDIUM,...)])
    return GuardResult(allowed=True)
```

- **Step 3.5** `app/security/engine.py`：`ToolGuardEngine`
  - 加载所有 Guardian；`evaluate(tool_name, args) -> GuardResult`（合并 findings，取最高 severity）。
  - 按 `TOOL_GUARD_LEVEL` 决策：OFF→全放行；AUTO→仅显式 denied 审批；SMART→INFO/LOW 放行、MEDIUM+ 审批；STRICT→全审批。

- **Step 3.6** `app/security/approval.py`：`ApprovalService`（内存待审队列 + `asyncio.Event`），供 API 查询与裁决。

- **Step 3.7** `app/middleware/tool_guard_mw.py`：

```python
class ToolGuardMiddleware(AgentMiddleware):
    name = "boetclaw_tool_guard"
    def __init__(self): self._engine = None
    def _lazy(self):
        if self._engine is None:
            from app.security.engine import ToolGuardEngine
            self._engine = ToolGuardEngine.from_settings()
        return self._engine
    def wrap_tool_call(self, request, handler):
        engine = self._lazy()
        name = request.tool_call.get("name",""); args = request.tool_call.get("args",{})
        res = engine.evaluate(name, args)
        if not res.allowed:
            emit_event(EventType.GUARD_BLOCK, {"tool":name,"reason":res.reason})
            return ToolMessage(content=f"[安全拦截] {res.reason}", tool_call_id=request.tool_call["id"], status="error")
        if res.requires_approval:
            emit_event(EventType.APPROVAL_REQUESTED, {"tool":name})
            decision = interrupt({"type":"tool_approval","tool":name,"args":args,"findings":[f.__dict__ for f in res.findings]})
            if decision != "approve":
                return ToolMessage(content="[用户拒绝执行]", tool_call_id=request.tool_call["id"], status="error")
            emit_event(EventType.GUARD_APPROVED, {"tool":name})
        return handler(request)
```

- **Step 3.8** 工厂中间件顺序固定：`[Observability, PlanGate, ToolGuard]`。
- **Step 3.9** API：`GET /api/v1/security/approvals`（待审列表）、`POST /api/v1/security/approvals/resume`（携带 `thread_id`、`decision`、`approval_id?` 恢复执行）、`GET/PUT /api/v1/security/config`（读改执行级别）。
- **Step 3.10** 单测 `tests/test_phase3_guardians.py`：越权路径被拒、shell 混淆被拒、普通工具放行、SMART 级别下 write_file 触发审批。

**验证**
```
chat 触发 execute_shell_command → GET /security/approvals 见待审 →
POST /security/approvals/resume {"thread_id":"...","approval_id":"...","decision":"reject"} → 工具不执行
file 工具写 .env → GUARD_BLOCK 事件
```

**交付物**：安全引擎、3 Guardian、审批服务、安全 API。
**DoD**：4 级策略行为符合矩阵；单测全绿；默认 SMART 生效。

---

## Phase 4 · 技能体系双层（2 天）

**目标**：技能池（共享）+ 工作区技能（副本），按 workspace+channel 动态解析，SKILL.md 热加载，安装前扫描。

**步骤**

- **Step 4.1** `skills_system/models.py`：`SkillInfo{name, description, path, languages, source, enabled}`、`SkillConflictError`。
- **Step 4.2** `skills_system/store.py`：`get_skill_pool_dirs()`（`backend/skills/`）、`get_workspace_skills_dir(agent_id)`（`workspace/agents/{id}/skills/`）、`read_skill_manifest(dir)`（解析 SKILL.md frontmatter）、`safe_skill_dir()`（路径安全校验）。
- **Step 4.3** `skills_system/scanner.py`：`SkillScanner.scan(skill_dir) -> list[Finding]` — 检测硬编码密钥（正则 `sk-`,`AKIA`,`password=`）、危险脚本（`os.system`,`eval`,`subprocess`）。
- **Step 4.4** `skills_system/pool_service.py`：`SkillPoolService`（list/install/remove 到池；install 前调 scanner）。
- **Step 4.5** `skills_system/workspace_service.py`：`SkillService(agent_id)`（从池复制到工作区、启用/禁用、`list_effective()`）。
- **Step 4.6** `skills_system/registry.py`：`resolve_effective_skills(workspace_dir, channel) -> list[str]`（返回技能目录路径列表，供 `create_deep_agent(skills=...)`）。
- **Step 4.7** 工厂 `build(skills=resolve_effective_skills(...))` 接入。
- **Step 4.8** API：`GET /api/v1/skills`（池+工作区）、`POST /api/v1/skills/install`、`POST /api/v1/skills/{name}/enable`、`POST /api/v1/skills/scan`。
- **Step 4.9** 热加载计划：`POST /api/v1/skills/reload` 用于重建对应 Workspace 的 agent；已在 Phase 33 落地，技能变更后可刷新已加载 Agent。
- **Step 4.10** 内置技能扩展：新增 `skills/pdf-form/`、`skills/office-doc/`、`skills/file-reader/` 的 SKILL.md。

**验证**：新增一个 SKILL.md → `GET /skills` 可枚举、`POST /skills/scan` 可扫描；完整 reload 验证转 Phase 15；含 `sk-xxx` 的技能被 scan 拦截。
**DoD**：池/工作区解析正确；扫描拦截生效；单测 `test_phase4_skills.py` 绿。

---

## Phase 5 · 多智能体 Workspace（2.5 天）

**目标**：多个隔离 Workspace，各自独立文件系统/记忆/技能/配置；4 级路由。

**步骤**

- **Step 5.1** `agents/workspace.py`：

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
@dataclass
class Workspace:
    agent_id: str
    root: Path
    config: dict[str, Any] = field(default_factory=dict)
    agent: Any = None            # 懒加载的 create_deep_agent 实例
    def skills_dir(self) -> Path: return self.root / "skills"
```

- **Step 5.2** `agents/multi_agent_manager.py`：

```python
import asyncio
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver
from app.core.agent_factory import BoetClawAgentFactory
from app.skills_system.registry import resolve_effective_skills

class MultiAgentManager:
    def __init__(self, root):
        self._root = root; self._ws: dict[str, Workspace] = {}
        self._locks: dict[str, asyncio.Lock] = {}
    async def get_agent(self, agent_id: str) -> Workspace:
        if agent_id in self._ws and self._ws[agent_id].agent: return self._ws[agent_id]
        lock = self._locks.setdefault(agent_id, asyncio.Lock())
        async with lock:
            if agent_id in self._ws and self._ws[agent_id].agent: return self._ws[agent_id]
            ws = Workspace(agent_id=agent_id, root=self._root/agent_id)
            ws.root.mkdir(parents=True, exist_ok=True)
            ws.agent = BoetClawAgentFactory.build(
                skills=resolve_effective_skills(ws.root, channel="console"),
                backend=FilesystemBackend(root_dir=str(ws.root)),
                checkpointer=MemorySaver(),
                extra_middleware=_full_stack(),   # PlanGate+ToolGuard
            )
            self._ws[agent_id] = ws
            return ws
    def list_agents(self): return list(self._ws.keys())
```
  > `FilesystemBackend` 构造参数名以实测为准（Step 5.6 校正：`.venv` 内 `inspect.signature(FilesystemBackend.__init__)`）。

- **Step 5.3** `agents/agent_context.py`：4 级路由：

```python
def resolve_agent_id(*, explicit=None, request=None, header=None) -> str:
    if explicit: return explicit
    if request and getattr(request.state, "agent_id", None): return request.state.agent_id
    if header: return header
    return settings.default_agent_id
```

- **Step 5.4** FastAPI 依赖注入：从 `X-Agent-Id` header / body / 默认解析 agent_id，路由到对应 Workspace。
- **Step 5.5** API：`GET /api/v1/agents`、`POST /api/v1/agents`（创建）、`DELETE /api/v1/agents/{id}`、`GET /api/v1/agents/{id}`。chat/tasks 接受 `agent_id`。
- **Step 5.6** 校正 backend 构造签名，联调隔离性。
- **Step 5.7** 单测：两 agent 写同名文件互不可见；懒加载并发（`asyncio.gather` 10 请求）只初始化一次。

**验证**：创建 `agentA`/`agentB`，各自 chat 写文件，互相 `ls` 不可见。
**DoD**：隔离性、路由优先级、并发懒加载单测全绿。

---

## Phase 6 · Provider 抽象 + 本地模型（2 天）

**目标**：统一模型提供商抽象，支持 OpenAI/Anthropic/Ollama，能力探测缓存。

**步骤**

- **Step 6.1** `providers/base.py`：`ModelInfo`、`ProviderInfo`、`Provider(ABC)`（`get_chat_model`、`list_models`、`check_connection`）。
- **Step 6.2** `providers/manager.py`：`ProviderManager`（单例，注册/获取 provider，`model_string` 解析 `provider:model`）。
- **Step 6.3** 实现 `openai_provider.py`、`anthropic_provider.py`、`ollama_provider.py`（`ChatOllama`，读 `OLLAMA_BASE_URL`）。
- **Step 6.4** `providers/capability_cache.py`：`get_capability_cache()`，`learn(model_key, cap, value)` 落盘 JSON（`workspace/.cache/capabilities.json`）。
- **Step 6.5** 工厂 `model` 参数改由 `ProviderManager.get_chat_model(settings.model_string)` 提供实例（保留字符串兼容）。
- **Step 6.6** API：`GET /api/v1/providers`、`GET /api/v1/providers/{name}/models`、`POST /api/v1/providers/{name}/check`。
- **Step 6.7** 单测 + Ollama 连通性可选跳过（无本地模型时 `pytest.mark.skipif`）。

**验证**：`GET /providers` 列出已配置 provider；切换 `LLM_PROVIDER=ollama` 后 `/providers/ollama/check` 反映连通性。
**DoD**：三 provider 可实例化；能力缓存读写正常。

---

## Phase 7 · 记忆与上下文策略（1.5 天）

**目标**：记忆后端可选（文件/Store），自动化触发不写长期记忆，上下文压缩策略明确。

**步骤**

- **Step 7.1** `memory/context_policy.py`：`AUTOMATION_SKIP_SOURCES={"cron","heartbeat"}`；`should_persist_memory(source) -> bool`。
- **Step 7.2** 工厂接入 `memory=[AGENTS.md]` 已有；新增可选 `store=`（`StoreBackend` 用于跨线程长期记忆）。
- **Step 7.3** 请求上下文加 `source` 字段（`user|cron|heartbeat|channel`），在 invoke 时透传；自动化来源跳过记忆写入。
- **Step 7.4** 采用 DeepAgents 内置 `SummarizationMiddleware`（可选加入中间件栈，配置阈值）。
- **Step 7.5** 单测：cron 来源请求不产生记忆写事件。

**DoD**：来源区分生效；摘要中间件可开关。

---

## Phase 8 · 渠道网关抽象与扩展（2 天）

**目标**：抽象 `BaseChannel`，重构现有钉钉/飞书/QQ，新增 Telegram（及 Discord 可选），统一队列与渲染。

**步骤**

- **Step 8.1** `services/gateway/base.py`：`BaseChannel(ABC)`（`channel`、`parse_incoming`、`send_reply`、`verify_signature`）+ 统一 `GatewayMessage`/`GatewayResponse`（迁移现有）。
- **Step 8.2** `services/gateway/renderer.py`：`MessageRenderer` + `RenderStyle`（markdown/plain/card），按渠道适配。
- **Step 8.3** `services/gateway/manager.py`：`ChannelManager`（注册表 + 每渠道 `asyncio.Queue(maxsize=1000)` + `_process_batch` 消费 → 建任务 → 回发）。
- **Step 8.4** 迁移 `channels/dingtalk.py`、`feishu.py`、`qq.py`（从现有 `router.py` 拆分）。
- **Step 8.5** 新增 `channels/telegram.py`（`python-telegram-bot` webhook 或长轮询）；`discord.py` 可选。
- **Step 8.6** Webhook 路由复用现有 `gateway.py`，改为经 `ChannelManager` 入队。
- **Step 8.7** 回发实现：钉钉/飞书用真实 API（access_token 获取 + 发消息），替换现有 stub。
- **Step 8.8** 单测：各渠道 `parse_incoming` 正确解析样例 payload；队列满时丢弃/降级策略。

**验证**：本地用 curl 模拟各渠道 webhook payload → 建任务 → （mock）回发。
**DoD**：≥4 渠道解析正确；队列上限生效；钉钉/飞书真实回发（有凭据时）。

---

## Phase 9 · 定时任务 + 心跳（1.5 天）

**目标**：APScheduler 驱动的 Cron 任务与心跳自检，来源标记为自动化。

**步骤**

- **Step 9.1** 重构 `services/task_scheduler.py`：内嵌 `AsyncIOScheduler`；`CronJob{id,name,cron,prompt,channel,agent_id,enabled}` 持久化到 JSON。
- **Step 9.2** `add_cron_job` / `remove` / `list`；触发时以 `source="cron"` 调 agent → 结果回发指定渠道。
- **Step 9.3** `services/heartbeat.py`：按 `HEARTBEAT_INTERVAL_MINUTES` 用 `HEARTBEAT_PROMPT` 问 agent，`source="heartbeat"`，回发上次频道。
- **Step 9.4** 生命周期：Phase2 启动时 `scheduler.start()`；lifespan 关闭时 `scheduler.shutdown()`。
- **Step 9.5** API：`GET/POST/DELETE /api/v1/tasks/cron`、`GET/PUT /api/v1/tasks/heartbeat`。
- **Step 9.6** 单测：注册每分钟任务（用短间隔）触发一次；来源不写记忆（依赖 Phase 7）。

**验证**：注册 `*/1 * * * *` 任务，1 分钟内触发 `CRON_TRIGGER` 事件。
**DoD**：Cron/心跳按时触发；自动化来源不污染记忆。

---

## Phase 10 · 插件系统 + 魔法命令（1.5 天）

**目标**：插件加载（tool/hook/command 等），/slash 命令快速控制。

**步骤**

- **Step 10.1** `plugins/architecture.py`：`PluginType(Enum)`（tool/provider/hook/command/frontend/general）、`PluginManifest`。
- **Step 10.2** `plugins/loader.py`：扫描 `backend/plugins_ext/*/manifest.json`，动态 import，注册到 `registry.py`。
- **Step 10.3** 插件工具经 `__all__` 自动发现，但**未在 config 启用则不注册**（安全默认，对标 QwenPaw）。
- **Step 10.4** `commands/registry.py`：注册 `/new`（新线程）、`/clear`（清历史）、`/stop`（取消运行）、`/plan`（进规划态）、`/restart`。
- **Step 10.5** chat 路由前置解析：消息以 `/` 开头 → 命中命令 → 执行控制逻辑（不进 LLM）。
- **Step 10.6** API：`GET /api/v1/plugins`、`POST /api/v1/plugins/reload`、`GET /api/v1/commands`。
- **Step 10.7** 单测：`/new` 切换 thread_id；未启用插件工具不出现在 `/tools`。

**DoD**：≥3 命令生效；插件安全默认（不启用不注册）验证通过。

---

## Phase 11 · 前端控制台扩展（3 天）

**目标**：在现有 React 基础上补齐首版管理控制台与 HITL 交互，覆盖 G9 六类能力。  
**审计后状态**：本阶段代码交付已完成，但产品闭环仍为“单页控制台 + 模态 Tab”，未形成页面级路由、深链和完整生命周期管理；因此 Phase 11 视为“控制台首版完成”，后续由 Phase 14-16 继续闭环。

**步骤**

- **Step 11.1** `services/api.ts` 扩展：新增 skills/agents/security/providers/cron 接口封装 + plan/approval SSE 处理。
- **Step 11.2** 新增 `components/AgentSwitcher.tsx`：顶栏切换/创建 Agent（带 `X-Agent-Id`）。
- **Step 11.3** `components/PlanConfirm.tsx`：收到 `plan_confirm` interrupt → 展示 todos → 批准/拒绝/编辑 → 调 confirm API。
- **Step 11.4** `components/ApprovalCard.tsx`：工具审批弹窗（findings 展示 + 批准/拒绝）。
- **Step 11.5** `components/SkillsManager.tsx`：技能池/工作区列表、启用开关、安装、扫描结果。
- **Step 11.6** `components/ProviderSettings.tsx`：provider/模型选择、连通性检测。
- **Step 11.7** `components/CronManager.tsx`：定时任务 CRUD、心跳配置。
- **Step 11.8** 追踪面板增强：按 trace 分组展示 thinking/tool/subagent/guard 事件时间线。
- **Step 11.9** `npm run build` 通过（TS 严格模式）。

**实际交付核对**：
- `AgentSwitcher` 已实现切换/创建，但未接入删除、详情、运行历史、文件浏览。
- `PlanConfirm` 已支持批准/拒绝；`edit` 请求字段存在但前端未提供编辑计划 UI。
- `ApprovalCard` 已轮询待审批并可批准/拒绝；缺安全配置页、审批历史和审批与 thread 的强关联可视化。
- `SkillsManager` 已支持池/工作区、添加、启停、扫描；缺安装入口、编辑、删除、扫描详情。
- `ProviderSettings` 已支持列表、模型、检测；缺 API Key/base_url/default model 的 UI 写入。
- `CronManager` 已支持创建/删除 Cron 和心跳开关；缺 Cron 编辑、启停、运行历史。
- `PluginsManager` 已补充到控制台；当前只读 + reload，缺启用/停用、安装、详情。
- `SidePanel` 已按类别显示追踪事件；缺独立 `/trace/:id` 深链页面。

**DoD（首版控制台）**：`npm run build` 无错误；聊天、计划确认、审批、技能、模型、定时、插件、追踪首版可用。  
**未闭环转入**：Phase 14-16。

---

## Phase 12 · 可观测性强化（1 天）

**步骤**
- **Step 12.1** OpenTelemetry：`opentelemetry-instrumentation-fastapi` 注入 FastAPI，span 关联 trace_id。
- **Step 12.2** LangSmith 可选：`LANGCHAIN_TRACING_V2=true` 时 DeepAgents 自动上报（已有 env）。
- **Step 12.3** `GET /api/v1/monitor/trace/{trace_id}/timeline`：结构化时间线（含 guard/plan/subagent）。
- **Step 12.4** 事件持久化：`TraceStore` 增加落盘（JSONL），重启不丢近期链路。

**DoD**：完整链路可查；OTel span 生成；可选 LangSmith 上报正常。

---

## Phase 13 · 部署与文档（1 天）

**步骤**
- **Step 13.1** 更新 `Dockerfile`（多阶段，含前端构建）、`docker-compose.yml`（backend+frontend+可选 ollama）。
- **Step 13.2** `scripts/install.ps1` / `install.sh`（零配置安装：venv + npm + .env 初始化）。
- **Step 13.3** 更新 `README.md`：架构、快速开始、各模块配置、API 索引、渠道接入指引。
- **Step 13.4** `docs/`：补 `ARCHITECTURE.md`、`API.md`、`CHANNELS.md`、`SECURITY.md`。
- **Step 13.5** 冒烟：`docker compose up` 后 `/docs` 与前端可访问。

**DoD**：一键部署可用；文档齐全；冒烟通过。

---

## Phase 14 · 产品路由与管理闭环补强（已完成）

**目标**：基于审计报告补齐最影响业务闭环的前端页面级路由、任务生命周期、安全配置、Agent 工作区和会话历史。已于 2026-07-14 完成，详见 `docs/PROGRESS.md` Phase 14.1-14.6 实现记录。

**步骤**
- [x] **Step 14.1** 引入轻量客户端路由（History API 等价路由层），至少提供：
  - `/chat`、`/chats`、`/chats/:threadId`
  - `/tasks`、`/tasks/:taskId`
  - `/agents`、`/agents/:agentId`
  - `/trace/:traceId`
  - `/settings/security`、`/settings/providers`
- [x] **Step 14.2** 任务页面闭环：接入 `GET /tasks/{id}`、`POST /tasks/{id}/run`、`POST /tasks/{id}/cancel`；补状态筛选、重跑、取消、Trace 跳转。
- [x] **Step 14.3** Agent 工作区页：接入 `GET/DELETE /agents/{agent_id}`；展示 root、loaded、skills_count、config、最近运行；补删除非 default Agent。
- [x] **Step 14.4** 安全设置页：接入 `GET/PUT /security/config`；展示 Guard level、enabled、待审批、审批历史（已实现运行期审批历史接口）。
- [x] **Step 14.5** Provider 配置页：新增后端配置写入接口，提供 `PUT /providers/{name}/config`、`PUT /providers/default`。
- [x] **Step 14.6** 会话历史：新增 JSON 会话持久化，提供会话列表、恢复、搜索、导出。

**DoD**：用户可通过 URL 直达任务、Agent、Trace、安全与模型配置；任务可重跑/取消；安全策略可在 UI 修改；会话刷新后可恢复。当前已完成；Provider 配置与审批历史为运行期写入/内存历史，后续可演进为 `.env` 或数据库持久化。

---

## Phase 15 · 扩展治理与运维闭环（已完成）

**目标**：补齐技能、插件、MCP、渠道、调度的治理页面与审计记录。已完成 15.1-15.5，详见 `docs/PROGRESS.md`。

**步骤**
- [x] **Step 15.1** 技能治理：前端接入 `POST /skills/install`；补技能详情、文件查看、编辑、删除、扫描详情；已新增删除、文件读写与扫描报告接口。
- [x] **Step 15.2** 插件治理：新增启用/停用、详情、安装接口与 UI；插件启停已支持运行期更新并持久化写入 `backend/.env`。
- [x] **Step 15.3** MCP 管理：接入 `GET /tools/mcp/servers`、`POST /tools/mcp/reload`；展示 server 状态、工具列表、工具参数详情与重载结果。
- [x] **Step 15.4** 渠道运维：新增渠道运维设置页；展示配置状态、队列深度、消息历史、失败重试、回发记录。
- [x] **Step 15.5** 调度增强：Cron 编辑、启停、手动触发、运行历史、失败原因与渠道回发状态。

**DoD**：扩展能力不再依赖纯手工改环境变量；关键运维对象可看状态、可操作、可追踪。当前技能、插件、MCP、渠道、调度已具备管理入口；插件启停与 Provider 配置均已持久化到 `.env`。

---

## Phase 16 · 钻井领域数据与产物中心（已完成）

**目标**：让 BoetClaw 从“钻井智能体外壳 + 模拟工具”进入真实业务闭环，沉淀领域对象与 Agent 产物。已完成领域模型、页面、工具数据源、产物中心和 LAS 导入闭环。

**步骤**
- [x] **Step 16.1** 新增领域对象：`Well`、`WellboreSection`、`DailyReport`、`DrillingParam`、`LasFile`，已用 JSON 文件索引落地并提供领域 API。
- [x] **Step 16.2** 新增领域路由与页面：`/wells`、`/wells/:wellId`、`/reports`、`/params`、`/las/import` 已接入。
- [x] **Step 16.3** 将 `query_drilling_params` 从模拟数据切换为真实数据源适配层，保留 mock 作为开发 fallback。
- [x] **Step 16.4** 产物中心：`/artifacts` 已接入；支持图表/代码预览、下载、关联任务/Trace/井号元数据预留。
- [x] **Step 16.5** LAS 导入与质量检查：已实现轻量 LAS 文本解析，产出结构化曲线 JSON 数据与质量报告。

**DoD**：一次真实井数据导入后，可通过 Agent 查询参数、生成图表/日报、在产物中心查看输出，并可追溯到任务和 Trace。当前已具备井/日报/参数/LAS 数据沉淀、参数工具读取、产物预览下载与元数据关联预留。

---

## Phase 17 · 审计遗留闭环补强（已完成）

**目标**：继续收口 Phase 14-16 后仍显式记录的遗留项，使已预留的页面与元数据能力形成可追踪闭环。

**步骤**
- [x] **Step 17.1** Agent 工作区运行历史与文件索引：新增 `GET /agents/{agent_id}/files`、`GET /agents/{agent_id}/history`；前端 `/agents/:agentId` 展示 files 目录索引、任务历史和会话历史。
- [x] **Step 17.2** Agent 产物与任务/Trace/井号自动写入侧车元数据：图表/代码生成链路已在产出文件时自动补写 `.meta.json`，包含 task、trace、run、agent、well 关联字段。

**DoD**：Agent 工作区可查看其文件产物和历史运行；产物中心的任务、Trace、井号关联不再只依赖手工侧车文件。当前已完成。

---

## Phase 19 · 安全审计持久化补强（已完成）

**目标**：将运行期安全审批记录沉淀到工作区文件，避免服务重启后审批审计历史丢失。

**步骤**
- [x] **Step 19.1** 审批历史 JSON 持久化：`ApprovalService` 已在创建和裁决审批时写入 `workspace/security/approval_history.json`，并在服务初始化时自动加载历史记录；现有 `/security/approvals/history` 响应结构保持不变。

**DoD**：审批历史可跨服务重启恢复；安全设置页继续通过原接口查看历史；单测覆盖创建、裁决、落盘、恢复流程。当前已完成。

---

## Phase 20 · Provider 配置持久化补强（已完成）

**目标**：让模型 Provider 设置页的运行期配置写入具备重启后保留能力，减少用户重复配置 API Key、base_url 和默认模型。

**步骤**
- [x] **Step 20.1** Provider `.env` 持久化：`PUT /providers/{name}/config` 已将 OpenAI、Anthropic、Ollama 的 API Key/base_url 写入 `backend/.env`；`PUT /providers/default` 已将 `LLM_PROVIDER`、`LLM_MODEL` 写入 `backend/.env`；现有运行期 settings 更新与接口响应保持不变。

**DoD**：通过 Provider API 修改配置后，运行期立即生效，并写入 `.env` 供后续服务启动加载；单测覆盖临时 `.env` 的更新与默认模型持久化。当前已完成。

---

## Phase 21 · Plan 编辑与历史审计补强（已完成）

**目标**：补齐计划确认中的 edit 分支与历史审计，让 `/plan` 不只支持批准/拒绝，也能记录用户编辑后的计划与确认轨迹。

**步骤**
- [x] **Step 21.1** Plan 编辑确认：`PlanConfirm` 支持编辑计划文本并以 `decision=edit`、`edited_todos` 提交；后端 `confirm_plan()` 使用 `Command(resume={"decision":"edit","edited_todos":[...]})` 恢复图。
- [x] **Step 21.2** Plan 历史审计：新增 `workspace/plans/plan_history.json`，记录计划创建、批准、拒绝、编辑和响应摘要；新增 `GET /agent/plan/history` 查询接口。

**DoD**：用户可在前端编辑计划后继续执行；计划创建和确认动作可按 thread 查询审计历史；单测覆盖 approve 与 edit 恢复载荷及历史记录。当前已完成。

---

## Phase 22 · Trace 时间线详情增强（已完成）

**目标**：补齐可观测性页面的细粒度运行详情，让 `/trace/:traceId` 不只展示原始事件，还能看到结构化时间线、事件间隔、分类统计和总耗时。

**步骤**
- [x] **Step 22.1** Timeline 详情字段：`build_timeline()` 已为每个事件补充 `sequence`、`offset_ms`、`delta_ms`，并在 trace 级别返回 `started_at`、`ended_at`、`duration_ms`。
- [x] **Step 22.2** Trace 页面详情：前端 `/trace/:traceId` 已接入 `GET /monitor/trace/{trace_id}/timeline`，展示事件数、总耗时、分类统计和按序事件详情，同时保留原始事件侧栏。

**DoD**：用户可通过 Trace 深链查看结构化耗时细节；后端单测覆盖时间线持续时间和事件间隔；前端构建通过。当前已完成。

---

## Phase 23 · API 鉴权与限流补强（已完成）

**目标**：补齐 G5 高可用后端中的 API 访问保护，支持本地单用户部署下的可选 Bearer Token 鉴权与轻量限流，同时保持零配置开发体验。

**步骤**
- [x] **Step 23.1** API Token 鉴权：新增 `ApiSecurityMiddleware`，当 `API_TOKEN` 非空时，`/api/v1/*` 需要 `Authorization: Bearer <token>` 或 `X-API-Token`；默认空 token 时保持开放。
- [x] **Step 23.2** API 内存限流：新增 `API_RATE_LIMIT_PER_MINUTE`，按客户端 IP 对 `/api/v1/*` 做每分钟请求数限制；默认 `0` 关闭限流。
- [x] **Step 23.3** 健康检查豁免：`/api/v1/monitor/health` 不受鉴权和限流影响，避免 Docker healthcheck 与外部探活被阻断。

**DoD**：未配置 token 时现有开发流程不受影响；配置 token 时 API 拒绝未授权请求；限流超过阈值返回 429；健康检查始终可访问；单测覆盖鉴权、健康豁免和限流。当前已完成。

---

## Phase 24 · 任务持久化与恢复补强（已完成）

**目标**：将后台任务从纯内存表扩展为 JSON 持久化，避免服务重启后任务列表、结果、Trace 关联和 Agent 历史丢失。

**步骤**
- [x] **Step 24.1** 任务 JSON 持久化：`TaskScheduler` 已读写 `workspace/tasks/task_history.json`，创建任务和状态更新后自动落盘。
- [x] **Step 24.2** 重启恢复：服务启动时自动加载历史任务；若发现重启前处于 `running` 的任务，则标记为 `failed` 并记录重启中断原因，避免任务永久显示运行中。

**DoD**：任务创建、完成、失败、取消状态可跨服务重启恢复；Agent 工作区历史仍可基于任务 metadata 聚合；单测覆盖创建/更新落盘和 running 任务恢复逻辑。当前已完成。

---

## Phase 25 · 渠道访问白名单补强（已完成）

**目标**：补齐渠道级访问控制，支持按平台配置允许访问的 `user_id` 白名单，拒绝非白名单消息并留下可审计记录。

**步骤**
- [x] **Step 25.1** JSON 白名单存储：新增 `workspace/access_control.json` 读写，空白名单保持兼容放行。
- [x] **Step 25.2** 网关入队拦截：`ChannelManager` 在消息入队前校验 `allowed_users`，被拒消息记录为 `denied`，并写入 `GATEWAY_MESSAGE{action:"denied"}`。
- [x] **Step 25.3** 管理 API：新增 `GET/PUT /api/v1/gateway/access-control`，支持查询和更新各渠道白名单。

**DoD**：默认无配置时现有渠道消息不受影响；配置白名单后，非白名单用户不会进入队列或 fallback 后台任务；消息历史可查拒绝原因；单测覆盖配置持久化、拒绝和放行路径。当前已完成。

---

## Phase 26 · 渠道访问控制页面闭环（已完成）

**目标**：将 Phase 25 的渠道 `allowed_users` 白名单管理 API 接入 `/settings/channels`，让运维人员可在控制台直接查看、编辑和保存渠道访问白名单。

**步骤**
- [x] **Step 26.1** 前端 API 接入：新增 `fetchGatewayAccessControl()` 与 `updateGatewayAccessControl()`，定义 `GatewayAccessControl` 类型。
- [x] **Step 26.2** 渠道页白名单面板：`ChannelsManager` 加载渠道状态、消息历史和访问控制配置；按渠道展示多行 `user_id` 输入框，支持逗号或换行分隔。
- [x] **Step 26.3** 拒绝状态可视化：消息历史筛选增加 `denied` 状态，便于查看非白名单拒绝记录。

**DoD**：用户可在 `/settings/channels` 完成白名单查看与保存；空输入保持渠道开放；保存后后端按 `workspace/access_control.json` 即时生效；前端构建通过。当前已完成。

---

## Phase 27 · 插件启停持久化补强（已完成）

**目标**：将插件治理页的启用/停用操作从运行期状态扩展为可重启恢复的配置写入，避免服务重启后 `ENABLED_PLUGINS` 回退。

**步骤**
- [x] **Step 27.1** `.env` 持久化：插件启停 API 更新 `settings.enabled_plugins` 后同步写入 `backend/.env` 的 `ENABLED_PLUGINS`。
- [x] **Step 27.2** 回归测试：插件安装/详情/启停测试覆盖启用写入、停用清空、加载失败仍保留启用配置。

**DoD**：通过 `/api/v1/plugins/{name}/enabled` 启停插件后，运行期插件注册立即刷新，`ENABLED_PLUGINS` 同步持久化；重启后可按 `.env` 恢复启用状态；单测覆盖持久化路径。当前已完成。

---

## Phase 28 · LAS 文件上传导入闭环（已完成）

**目标**：补齐 Phase 16.5 留下的 LAS 上传能力，使 `/las/import` 不再只能依赖服务器本地路径，可直接选择本地 LAS 文件上传、解析、质检和沉淀曲线数据。

**步骤**
- [x] **Step 28.1** Multipart 上传 API：新增 `POST /api/v1/domain/las/upload`，接收 `well_id`、`filename` 与上传文件，保存到 `workspace/domain/las_uploads/`。
- [x] **Step 28.2** 复用解析沉淀链路：上传后复用 `import_las_file()`，生成 `LasFile` 记录、质量摘要与 `las_curves/{las_id}.json` 曲线数据。
- [x] **Step 28.3** 前端上传入口：`/las/import` 支持文件选择上传并质检，同时保留服务器路径导入。

**DoD**：用户可从控制台上传 LAS 文件；上传文件安全落入 workspace；导入后列表展示曲线、深度范围、点数与空值数；后端测试覆盖上传接口，前端构建通过。当前已完成。

---

## Phase 29 · Prometheus Metrics 监控补强（已完成）

**目标**：补齐计划中 Metrics/Prometheus 可选项，在不引入额外依赖的前提下提供标准 Prometheus text exposition 指标端点。

**步骤**
- [x] **Step 29.1** Metrics API：新增 `GET /api/v1/monitor/metrics`，返回 `text/plain; version=0.0.4`。
- [x] **Step 29.2** 核心指标输出：覆盖任务状态计数、Trace 事件总数/类型计数、待审批数、网关队列深度。
- [x] **Step 29.3** 回归测试：补充 Prometheus 文本格式和关键指标断言。

**DoD**：监控系统可抓取 `/monitor/metrics`；核心运行状态以 Prometheus gauge 暴露；既有 `/monitor/stats` JSON 接口不受影响；单测覆盖指标端点。当前已完成。

---

## Phase 30 · Agent 产物关联筛选闭环（已完成）

**目标**：补齐“产物与 Agent 运行自动关联”的页面与 API 闭环，让产物中心可按 Agent 追踪生成物。

**步骤**
- [x] **Step 30.1** 产物 API 增强：`/files/artifacts` 返回侧车元数据中的 `agent_id`，并支持 `?agent_id=` 过滤。
- [x] **Step 30.2** 产物中心接入：`/artifacts` 页面显示产物关联 Agent，并支持输入 Agent ID 筛选。
- [x] **Step 30.3** 回归测试：覆盖 `agent_id` 返回、命中过滤和未命中过滤。

**DoD**：Agent 执行生成的图表/代码可在产物中心看到来源 Agent；用户可按 Agent ID 过滤产物；既有 kind/well 过滤与下载预览不受影响。当前已完成。

---

## Phase 31 · Plan 确认失败恢复审计（已完成）

**目标**：补齐 G1 中“失败恢复记录”口径，让 `/plan` 确认恢复在 checkpoint 丢失、图恢复异常等失败场景下也能写入计划历史，避免确认动作失败后无审计线索。

**步骤**
- [x] **Step 31.1** 失败记录落盘：`confirm_plan()` 捕获恢复异常，写入 `workspace/plans/plan_history.json`，action 使用 `<decision>_failed`，response 保存错误摘要。
- [x] **Step 31.2** 行为兼容：失败记录写入后重新抛出原异常，保持现有 API 错误语义，不伪装为成功恢复。
- [x] **Step 31.3** 回归测试：覆盖 Plan approve 恢复失败时的历史记录写入、错误信息保存和异常继续抛出。

**DoD**：Plan 创建、批准、拒绝、编辑和确认恢复失败均可在计划历史中追溯；失败路径不会吞掉真实异常；Plan 回归测试覆盖成功、编辑和失败审计。当前已完成。

---

## Phase 32 · Console 登录 JWT 闭环（已完成）

**目标**：补齐 I.3 中 Console 登录可选增强，让本地/单用户部署可以通过 `CONSOLE_PASSWORD` 开启控制台密码登录，并签发短期 JWT 维持前端会话。

**步骤**
- [x] **Step 32.1** Console Auth API：新增 `GET /api/v1/auth/status`、`POST /api/v1/auth/login`、`POST /api/v1/auth/logout`。
- [x] **Step 32.2** 短期 JWT：新增无外部依赖的 HMAC-SHA256 JWT 工具，使用 `CONSOLE_JWT_SECRET`/`API_TOKEN`/`CONSOLE_PASSWORD` 作为签名密钥来源，按 `CONSOLE_JWT_TTL_MINUTES` 过期。
- [x] **Step 32.3** 中间件兼容：`ApiSecurityMiddleware` 在 `CONSOLE_PASSWORD` 非空时保护 `/api/v1/*`，同时兼容原 `API_TOKEN`、`X-API-Token` 和 Console JWT cookie/Bearer。
- [x] **Step 32.4** 前端登录页：控制台启动时查询登录状态；需要登录时展示密码页；登录成功 token 存 `localStorage`，后端同时写入 HttpOnly cookie；顶部提供退出。
- [x] **Step 32.5** 回归测试与构建：覆盖未登录拒绝、错误密码、登录后访问、Bearer token 和登出失效；前端构建通过。

**DoD**：未配置 `CONSOLE_PASSWORD` 时保持零配置开放；配置后 Console/API 需要密码登录或 API Token；登录态有过期时间并可退出；多用户 RBAC 仍列为未来扩展。当前已完成。

---

## Phase 33 · 技能 Reload 与 Agent 重建闭环（已完成）

**目标**：补齐 Step 4.9 和 API 表中遗留的 `POST /api/v1/skills/reload`，让技能安装、编辑、启停后可以显式刷新已加载 Workspace Agent，使新技能配置在运行期生效。

**步骤**
- [x] **Step 33.1** MultiAgent 重建能力：`MultiAgentManager` 新增 `reload_agent(agent_id)`，对已加载工作区在同一 agent lock 下清空并重建 agent；未加载工作区只保持下次懒加载生效。
- [x] **Step 33.2** 全量已加载刷新：新增 `reload_loaded_agents()`，仅刷新当前内存中已加载的 Workspace，避免构建所有未使用 Agent。
- [x] **Step 33.3** Skills API：新增 `POST /api/v1/skills/reload`，支持 body `{agent_id?}`；未传 `agent_id` 时刷新所有已加载 Agent。
- [x] **Step 33.4** 回归测试：覆盖已加载 Agent 被重建、未加载 Agent 不被强制构建、响应 `reloaded/agents` 结构正确。

**DoD**：技能治理操作后可通过 reload API 刷新运行期 Agent；已加载 Agent 立即重建并读取最新技能目录；未加载 Agent 保持懒加载语义；单测覆盖 reload 路径。当前已完成。

---

## Phase 34 · 渠道消息历史持久化闭环（已完成）

**目标**：补齐 Phase 15.4 中“消息历史尚未落盘”的遗留项，将渠道消息审计从运行期内存列表扩展为 JSON 持久化，服务重启后仍可查看入队、失败、拒绝、回发等历史记录。

**步骤**
- [x] **Step 34.1** 历史落盘：`ChannelManager` 新增 `workspace/gateway/message_history.json` 读写，`record_message()` 写入内存后同步保存最近 500 条。
- [x] **Step 34.2** 恢复查询：服务初始化时加载历史 JSON，`message_history()` 继续返回原有字段结构，过滤参数保持兼容。
- [x] **Step 34.3** 重试边界：内存中保留 `_message` 用于运行期 retry，落盘剔除不可序列化对象；重启恢复的旧记录仅可审计，不伪造重试上下文。
- [x] **Step 34.4** 回归测试：覆盖历史文件写入、重启恢复查询、不可序列化字段不落盘和恢复记录无法重试。

**DoD**：渠道消息历史可跨服务重启恢复查询；既有 `/gateway/messages` API 与页面筛选不受影响；运行期失败消息仍可重试；单测覆盖持久化路径。当前已完成。

---

## Phase 35 · OpenTelemetry 控制台导出稳定性补强（已完成）

**目标**：收束测试和短生命周期进程退出时反复出现的 `ValueError: I/O operation on closed file` 非阻断噪声，保留 FastAPI OTel instrumentation 与 `boetclaw.trace_id` 关联，同时将控制台 span 导出改为显式启用。

**步骤**
- [x] **Step 35.1** 配置开关：新增 `OTEL_CONSOLE_EXPORTER=false`，默认不向 stdout/stderr 导出 span。
- [x] **Step 35.2** 初始化调整：`setup_otel()` 仍创建 `TracerProvider` 并注入 FastAPI；仅当 `settings.otel_console_exporter` 为 true 时才注册 `BatchSpanProcessor(ConsoleSpanExporter())`。
- [x] **Step 35.3** 回归验证：可观测性测试保持 OTel 幂等；渠道测试退出阶段不再出现关闭流异常。

**DoD**：默认测试和本地短生命周期命令不再打印 OTel 关闭流异常；需要调试 span 输出时可显式开启 `OTEL_CONSOLE_EXPORTER=true`；trace_id header 与 timeline/metrics 能力不受影响。当前已完成。

---

## Phase 36 · 渠道用户级限流防刷（已完成）

**目标**：补齐 Part N.2 中“渠道级每 user 每分钟消息上限，防刷”的要求，在不影响默认零配置渠道接入的前提下，为外部 webhook 增加按平台和 user_id 维度的轻量内存限流。

**步骤**
- [x] **Step 36.1** 配置项：新增 `GATEWAY_RATE_LIMIT_PER_MINUTE`，默认 `0` 表示关闭。
- [x] **Step 36.2** 限流器：`ChannelManager` 新增按 `platform:user_id` 的 60 秒滑动窗口计数，支持 webhook 与内部 `enqueue()` 双路径。
- [x] **Step 36.3** 拒绝审计：超限消息写入 `rate_limited` 状态，detail 为 `user_rate_limit`，并发出 `GATEWAY_MESSAGE{action:"rate_limited"}`。
- [x] **Step 36.4** fallback 边界：webhook 路由在入队前识别超限并直接返回 `Rate limited`，避免被原 queue fallback 作为后台任务继续执行。
- [x] **Step 36.5** 回归测试：覆盖 webhook 用户超限、队列不新增、审计记录写入，以及直接 `enqueue()` 超限拒绝。

**DoD**：默认关闭时现有渠道行为不变；开启后同一渠道同一用户每分钟超过阈值的消息不进入队列、不触发后台 fallback；超限记录可在 `/gateway/messages?status=rate_limited` 查询；单测覆盖限流路径。当前已完成。

---

## Phase 37 · 审批 Pending 重启失效审计（已完成）

**目标**：补齐 ToolGuard 审批在 MemorySaver 场景下的重启边界：审批历史已持久化，但重启前处于 `pending` 的审批无法继续 resume 原图中断点，不应继续显示为待审批。

**步骤**
- [x] **Step 37.1** 恢复语义：`ApprovalService` 加载历史时将持久化文件中的 `pending` 审批标记为 `expired`。
- [x] **Step 37.2** 列表边界：`list_pending()` 不返回 `expired`，避免前端继续展示不可恢复的审批卡片。
- [x] **Step 37.3** 历史可追溯：`expired` 状态继续保留在 `/security/approvals/history` 中，便于审计重启前未处理的审批。
- [x] **Step 37.4** 回归测试：覆盖 pending 审批重启后变为 expired、文件回写、待审批列表清空，并修复旧审批测试的 workspace 污染。

**DoD**：服务重启后不会出现无法恢复的 pending 审批；历史中可追溯过期审批；已批准/拒绝历史不受影响；单测覆盖恢复边界。当前已完成。

---

## Phase 38 · API Token 维度限流补强（已完成）

**目标**：补齐 Part N.2 中“按 token/IP 限流”的口径。原 API 限流只按客户端 IP 计数，同一代理或网关后的不同 API/Console token 会互相挤占限额；本阶段改为 token 优先、IP 兜底的限流分桶。

**步骤**
- [x] **Step 38.1** 限流 key：`ApiSecurityMiddleware` 新增 `_rate_key()`，优先使用 Bearer、`X-API-Token` 或 Console cookie token 的 SHA256 摘要作为分桶 key。
- [x] **Step 38.2** IP 兜底：无 token 请求继续按客户端 IP 限流，保持本地开放场景兼容。
- [x] **Step 38.3** Console 会话唯一性：Console JWT 增加 `jti`，确保同一秒内多次登录也会生成不同 token。
- [x] **Step 38.4** 回归测试：覆盖无 token IP 限流、同 token 超限、不同 token 独立分桶。

**DoD**：API 限流符合 token/IP 口径；不同 token 在同一 IP 下互不影响；限流 key 不保存明文 token；既有 API Token、Console 登录和健康检查豁免不受影响。当前已完成。

---

## Phase 39 · Provider 模型解析限流补强（已完成）

**目标**：补齐 Part N.2 中 Provider 级限流的轻量闭环，在不包裹 LangChain 模型运行对象的前提下，先对统一模型解析入口 `ProviderManager.get_chat_model()` 做 provider/model 维度的滑动窗口限流。

**步骤**
- [x] **Step 39.1** 配置项：新增 `PROVIDER_RATE_LIMIT_PER_MINUTE`，默认 `0` 关闭。
- [x] **Step 39.2** 限流器：新增 `providers/rate_limiter.py`，按 `provider:model` 维护 60 秒滑动窗口。
- [x] **Step 39.3** 统一入口接入：`ProviderManager.get_chat_model()` 在创建具体模型前调用限流器。
- [x] **Step 39.4** 回归测试：覆盖默认关闭、同 provider/model 超限、不同 model/provider 独立分桶。

**DoD**：默认行为不变；开启后重复解析同一 provider/model 会被限制；不同 provider 或 model 独立计数；单测覆盖限流器路径。当前已完成。后续如需精确限制每次 LLM `invoke/ainvoke`，可在模型 wrapper 层继续扩展。

---

## Phase 40 · MCP Recover 指标闭环（已完成）

**目标**：补齐 Metrics 章节中 `mcp_recover_total{result}` 的可观测指标，让 MCP reload/recover 操作的成功与失败可以被 Prometheus 抓取和告警。

**步骤**
- [x] **Step 40.1** 计数器：`MCPManager` 增加 `_recover_counts`，按 `success`/`failed` 记录 reload/recover 次数。
- [x] **Step 40.2** 事件审计：`reload()` 成功或失败时发出 `EventType.MCP_RECOVER` 事件；连接失败保持原有容错，未捕获异常继续向上抛出。
- [x] **Step 40.3** Metrics 输出：`/monitor/metrics` 增加 `boetclaw_mcp_recover_total{result="success|failed"}`。
- [x] **Step 40.4** 回归测试：覆盖 Prometheus 文本输出和 MCP reload 成功/失败计数。

**DoD**：MCP reload/recover 操作可被计数；成功与失败分开输出；连接失败不打断服务，未捕获异常仍向上抛出；metrics 与管理器行为均有单测覆盖。当前已完成。

---

## Phase 41 · Metrics 表核心计数补齐（已完成）

**目标**：继续补齐 M.3 Metrics 表中尚未输出的核心 Prometheus 指标，基于现有 Trace 事件聚合 Agent 运行、工具调用、Guard 拦截和 Provider 重试/解析事件。

**步骤**
- [x] **Step 41.1** Agent 运行计数：输出 `boetclaw_agent_runs_total{status}`，覆盖 started/completed/failed。
- [x] **Step 41.2** 工具调用计数：输出 `boetclaw_tool_calls_total{tool,status}`，覆盖 started/completed。
- [x] **Step 41.3** 安全与 Provider 计数：输出 `boetclaw_guard_blocks_total{guardian}` 与 `boetclaw_llm_retries_total{provider}`。
- [x] **Step 41.4** 回归测试：扩展 metrics 端点测试，隔离 TraceStore 后断言新增指标文本。

**DoD**：M.3 Metrics 表中的核心 Counter/Gauge 指标均有对应 Prometheus 文本输出；新增指标不引入外部依赖；现有 `/monitor/stats` 与既有 metrics 输出不受影响。当前已完成。

---

## Phase 42 · Agent 运行耗时 Histogram（已完成）

**目标**：补齐 M.3 Metrics 表中的 `agent_run_duration_seconds`，基于现有 `AGENT_START`/`AGENT_END` Trace 事件按 `run_id` 计算端到端运行耗时，并以 Prometheus histogram 文本输出。

**步骤**
- [x] **Step 42.1** 运行配对：按 `run_id` 记录 `AGENT_START` 时间，并与同 run 的 `AGENT_END` 配对。
- [x] **Step 42.2** Histogram 输出：新增 `boetclaw_agent_run_duration_seconds_bucket/count/sum`，使用固定秒级 buckets。
- [x] **Step 42.3** 容错口径：忽略无法解析时间戳、缺少 start/end 或负耗时的异常事件，不影响 metrics 端点。
- [x] **Step 42.4** 回归测试：扩展 metrics 测试，使用同一 `run_id` 构造 start/end 并断言 histogram 输出。

**DoD**：Prometheus 可抓取 Agent 端到端耗时分布；未完成运行不会污染 histogram；既有计数、任务、Trace、审批、网关和 MCP 指标不受影响。当前已完成。

---

## Phase 43 · 命令文案 i18n 轻量闭环（已完成）

**目标**：补齐 N.1 i18n 的最小可验证能力，先将 slash command 的帮助与响应文案抽到 `app/i18n` 字典，并支持请求级 `lang` 覆盖。

**步骤**
- [x] **Step 43.1** i18n helper：新增 `app/i18n`，提供 `normalize_lang()`、`t()` 与中英文消息字典。
- [x] **Step 43.2** 命令文案接入：`CommandRegistry` 使用翻译 key 输出 `/help` 描述和 `/new`、`/clear`、`/stop`、`/restart` 响应。
- [x] **Step 43.3** 请求级覆盖：`ChatRequest` 增加 `lang` 字段，`/agent/chat` 执行 slash command 时透传到命令上下文。
- [x] **Step 43.4** 回归测试：覆盖默认中文帮助、英文上下文和 chat API 的 `lang=en` 覆盖。

**DoD**：默认中文行为保持兼容；请求传入 `lang=en` 时命令帮助和响应返回英文；不影响 `/plan` 透传与普通消息进入 LLM。当前已完成。

---

## Phase 44 · i18n Header 覆盖补齐（已完成）

**目标**：补齐 N.1 中“请求级覆盖”的 HTTP header 入口，让 slash command 文案在未传 body `lang` 时也能根据 `Accept-Language` 返回中英文。

**步骤**
- [x] **Step 44.1** Header 解析：`/agent/chat` 调用 `lang_from_headers()`，读取 `Accept-Language` 并归一化 `en-US` 等区域语言。
- [x] **Step 44.2** 优先级：body `lang` 优先于 `Accept-Language`，两者缺失时回退配置 `LANG`。
- [x] **Step 44.3** 命令上下文透传：slash command 执行时传入解析后的语言，不影响普通 LLM 消息与 `/plan` 透传。
- [x] **Step 44.4** 回归测试：覆盖 header 英文覆盖，以及 body `lang=zh` 覆盖 header 英文的优先级。

**DoD**：`Accept-Language: en-US,en;q=0.9` 可让 `/help` 返回英文；body `lang` 可覆盖 header；默认中文行为不变。当前已完成。

---

## Phase 45 · 计划状态闭合审计（已完成）

**目标**：按“先检查计划”的要求，对 `PROGRESS.md` 全量清单进行状态一致性审计，闭合已完成但阶段标题仍显示进行中的记录。

**步骤**
- [x] **Step 45.1** 清单扫描：检查 `[ ]`、`[~]`、未完成、未实现、缺口等标记，确认当前全量任务项均已勾选。
- [x] **Step 45.2** 阶段状态修正：将子项已全部 `[x]` 的 Phase 14-17 标题由 `⏳` 修正为 `✅`。
- [x] **Step 45.3** 实现记录：在 `PROGRESS.md` 顶部追加计划状态闭合记录，说明检查口径、修改文件和问题解决。
- [x] **Step 45.4** 一致性验证：复查 Phase 14-17 标题、Phase 45 清单、M-AJ、G39 与实现记录同步。

**DoD**：进度文档不存在“子项全完成但阶段标题仍未闭合”的状态漂移；计划检查过程可追溯。当前已完成。

---

## Phase 46 · 安全提示 i18n 闭环（已完成）

**目标**：继续补齐 N.1 i18n 中“安全提示、审批文案”的最小闭环，将 ToolGuard 的安全拦截和用户拒绝执行提示接入 `app/i18n`。

**步骤**
- [x] **Step 46.1** i18n 上下文：`app/i18n` 增加运行时语言 ContextVar，`t()` 默认读取当前请求语言。
- [x] **Step 46.2** 安全文案字典：新增 `security.blocked`、`security.user_rejected` 中英文文案。
- [x] **Step 46.3** ToolGuard 接入：`ToolGuardMiddleware` 使用 `t()` 输出安全拦截和用户拒绝执行消息。
- [x] **Step 46.4** 回归测试：覆盖默认中文、英文安全拦截、英文拒绝执行路径。

**DoD**：默认中文安全提示保持兼容；请求语言上下文为英文时，ToolGuard 返回英文安全拦截/拒绝执行提示；既有审批与拦截逻辑不变。当前已完成。

---

# Part E. 里程碑与排期（建议）

| 里程碑 | 阶段 | 累计天 | 交付价值 |
|--------|------|--------|---------|
| **M-A 规划+安全执行闭环** | 0-3 | 7 | 类 Cursor 的规划-审批-执行（核心卖点） |
| **M-B 技能+多智能体** | 4-5 | 11.5 | 能力扩展 + 隔离多 Agent |
| **M-C 模型+记忆** | 6-7 | 15 | 本地模型 + 记忆策略 |
| **M-D 渠道+定时** | 8-9 | 18.5 | 多端接入 + 自动化 |
| **M-E 插件+前端+部署** | 10-13 | 25 | 首版产品化与部署闭环 |
| **M-F 页面路由+管理闭环** | 14 | 29 | 任务/Agent/安全/Provider/会话可深链管理 |
| **M-G 扩展治理+运维** | 15 | 32 | 技能/插件/MCP/渠道/调度可治理 |
| **M-H 钻井业务闭环** | 16 | 37 | 真实井数据、产物中心、业务对象闭环 |
| **M-I 审计遗留闭环** | 17 | 39 | Agent 文件/历史索引与产物元数据自动关联 |
| **M-J 安全审计持久化** | 19 | 40 | 审批历史可跨重启追溯 |
| **M-K Provider 配置持久化** | 20 | 41 | 模型配置写入 `.env` 并可重启恢复 |
| **M-L Plan 编辑审计** | 21 | 42 | 计划可编辑确认并可追溯 |
| **M-M Trace 时间线详情** | 22 | 43 | 运行耗时、事件间隔与分类详情可视化 |
| **M-N API 安全补强** | 23 | 44 | API Token 鉴权、限流与健康检查豁免 |
| **M-O 任务持久化** | 24 | 45 | 后台任务可跨重启恢复 |
| **M-P 渠道访问控制** | 25 | 46 | 渠道用户白名单与拒绝审计 |
| **M-Q 渠道访问控制页面** | 26 | 47 | 控制台可编辑渠道白名单 |
| **M-R 插件启停持久化** | 27 | 48 | 插件启用状态可重启恢复 |
| **M-S LAS 上传导入** | 28 | 49 | LAS 本地上传、解析与质检闭环 |
| **M-T Metrics 监控端点** | 29 | 50 | Prometheus 可抓取核心指标 |
| **M-U Agent 产物筛选** | 30 | 51 | 产物中心可按 Agent 追踪生成物 |
| **M-V Plan 失败审计** | 31 | 52 | 计划确认恢复失败也可追溯 |
| **M-W Console 登录** | 32 | 53 | 控制台可选密码登录与短期会话 |
| **M-X 技能 Reload** | 33 | 54 | 技能变更后可刷新已加载 Agent |
| **M-Y 渠道消息持久化** | 34 | 55 | 渠道消息审计可跨重启追溯 |
| **M-Z OTel 导出稳定** | 35 | 56 | 测试退出不再产生 OTel 关闭流噪声 |
| **M-AA 渠道防刷限流** | 36 | 57 | 渠道用户级消息限流与审计 |
| **M-AB 审批 Pending 失效** | 37 | 58 | 重启后待审批不过期误导 |
| **M-AC API Token 限流** | 38 | 59 | 同 IP 多 token 独立限流 |
| **M-AD Provider 限流** | 39 | 60 | 模型解析入口可按 provider/model 限流 |
| **M-AE MCP Recover 指标** | 40 | 61 | MCP reload/recover 成败可观测 |
| **M-AF Metrics 表补齐** | 41 | 62 | Agent/工具/Guard/Provider 核心计数可观测 |
| **M-AG Agent 耗时指标** | 42 | 63 | Agent 端到端运行耗时可观测 |
| **M-AH 命令 i18n** | 43 | 64 | slash command 文案支持中英文 |
| **M-AI i18n Header 覆盖** | 44 | 65 | Accept-Language 驱动命令文案语言 |
| **M-AJ 计划状态闭合** | 45 | 66 | 已完成阶段状态一致可追溯 |
| **M-AK 安全提示 i18n** | 46 | 67 | ToolGuard 安全提示支持中英文 |

> 关键路径 0→1→2→3 已完成，M-A 到 M-E 已具备可演示版本；M-F 到 M-H 是审计后确认的产品闭环补强路径。

# Part F. 风险登记册

| 风险 | 等级 | 缓解 |
|------|------|------|
| `interrupt()` resume 语义与预期不符 | 中 | ✅ `interrupt(value)`/`Command(resume=)` 已实测存在；Phase 2 Step 2.5 联调 resume 值传递 |
| `wrap_tool_call` 无法读 state 中 plan_phase | 中 | 用 `request` 属性实测；不行则改用 `before_model` 注入约束 |
| `FilesystemBackend` 构造参数名 | 低 | ✅ 已实测 `FilesystemBackend(root_dir, virtual_mode, max_file_size_mb)` |
| 多中间件顺序导致钩子冲突 | 中 | 固定顺序 + 单测覆盖 |
| 渠道真实 API 凭据缺失 | 低 | 无凭据走 mock，接口保持一致 |
| 并发 Workspace 初始化竞态 | 中 | `asyncio.Lock` + 双检；单测覆盖 |

# Part G. 总验收清单

- [x] G1 `/plan`→confirm→execute 闭环可复现（fake-agent 自动化覆盖；真实 LLM 需配置 Key）
- [x] G2 SKILL.md 池/工作区解析 + 扫描拦截
- [x] G3 两 Workspace 文件/记忆隔离 + 4 级路由
- [x] G4 ≥4 渠道 webhook→任务→回复，Trace 贯通（有凭据时真实回发，无凭据 stub/容错）
- [x] G5 OpenAPI 路由覆盖，SSE 可用，两阶段启动
- [x] G6 Trace 事件、统计与 timeline API 可查
- [x] G7 高危工具默认拦截+审批，越权路径被拒
- [x] G8 Cron/心跳触发链路与自动化来源记忆策略
- [x] G9 Web 控制台可用，`npm run build` 通过；页面级路由、任务生命周期、Agent/安全/Provider/会话管理闭环已补齐
- [x] G10 钻井业务闭环：真实井/井段/日报/LAS/参数库实体、领域页面、参数工具真实数据源与产物中心已落地
- [x] G11 Agent 工作区闭环：`/agents/:agentId` 可查看详情、技能聚合、运行历史和 files 目录索引
- [x] G12 产物追踪闭环：图表/代码生成后自动写入 task、trace、run、agent、well 侧车元数据并被产物中心读取
- [x] G13 安全审计闭环：审批历史 JSON 持久化，服务重启后可恢复查看
- [x] G14 Provider 配置闭环：API Key/base_url/default model 写入 `backend/.env` 并保持运行期生效
- [x] G15 Plan 编辑审计闭环：计划可编辑提交，创建/确认历史写入 JSON 并可查询
- [x] G16 Trace 详情闭环：`/trace/:traceId` 展示结构化时间线、总耗时、事件间隔和分类统计
- [x] G17 API 安全闭环：`API_TOKEN` Bearer 鉴权、`API_RATE_LIMIT_PER_MINUTE` 限流与健康检查豁免已落地
- [x] G18 任务持久化闭环：任务列表、状态、结果、Trace/run 和 metadata 写入 JSON 并可重启恢复
- [x] G19 渠道访问控制闭环：每渠道 `allowed_users` 白名单可配置，非白名单消息拒绝并进入审计历史
- [x] G20 渠道访问控制页面闭环：`/settings/channels` 可编辑白名单并筛选 `denied` 消息
- [x] G21 插件启停持久化闭环：`ENABLED_PLUGINS` 随 UI/API 启停同步写入 `.env` 并可重启恢复
- [x] G22 LAS 上传导入闭环：`/las/import` 支持本地文件上传，后端保存、解析、质检并沉淀曲线 JSON
- [x] G23 Metrics 监控闭环：`/monitor/metrics` 以 Prometheus 文本暴露任务、Trace、审批和网关队列指标
- [x] G24 Agent 产物筛选闭环：产物 API 与 `/artifacts` 页面均支持 `agent_id` 展示和过滤
- [x] G25 Plan 失败恢复审计闭环：确认恢复异常写入计划历史并保留原异常语义
- [x] G26 Console 登录闭环：`CONSOLE_PASSWORD` 开启密码登录，短期 JWT 保持会话并可退出
- [x] G27 技能 Reload 闭环：`/skills/reload` 可重建已加载 Agent，使技能变更运行期生效
- [x] G28 渠道消息历史持久化闭环：`/gateway/messages` 历史写入 JSON 并可重启恢复查询
- [x] G29 OTel 控制台导出稳定性闭环：默认关闭 ConsoleSpanExporter，保留 trace 关联且消除关闭流异常
- [x] G30 渠道用户级限流闭环：`GATEWAY_RATE_LIMIT_PER_MINUTE` 可限制同渠道同用户消息频率并记录审计
- [x] G31 审批 Pending 重启失效闭环：重启前未处理审批恢复为 `expired` 历史，不再进入待审批列表
- [x] G32 API Token 维度限流闭环：API 限流按 token 优先、IP 兜底分桶，避免同代理多 token 互相影响
- [x] G33 Provider 模型解析限流闭环：`PROVIDER_RATE_LIMIT_PER_MINUTE` 可按 provider/model 限制模型解析频率
- [x] G34 MCP Recover 指标闭环：`/monitor/metrics` 暴露 MCP reload/recover 成败计数
- [x] G35 Metrics 表核心计数闭环：`/monitor/metrics` 暴露 Agent 运行、工具调用、Guard 拦截和 Provider 重试/解析计数
- [x] G36 Agent 运行耗时指标闭环：`/monitor/metrics` 暴露 `boetclaw_agent_run_duration_seconds` histogram
- [x] G37 命令文案 i18n 闭环：slash command 帮助与响应支持默认中文和请求级英文覆盖
- [x] G38 i18n Header 覆盖闭环：`/agent/chat` 命令响应支持 `Accept-Language`，且 body `lang` 优先
- [x] G39 计划状态闭合审计：Phase 14-17 子项全完成后阶段标题同步为完成态
- [x] G40 安全提示 i18n 闭环：ToolGuard 安全拦截和拒绝执行文案支持请求语言上下文
- [x] 全量 `pytest` 绿；`docker compose config` 通过
- [x] `docker compose up` 端到端冒烟与前端浏览器回归

---

# 附录

## 附1. 核心数据模型字段表

| 模型 | 字段 |
|------|------|
| `AgentConfig` | agent_id, name, model, provider, skills[], memory_backend, tool_guard_level |
| `WorkspaceInfo` | agent_id, root, created_at, skills_count, thread_count |
| `SkillInfo` | name, description, path, languages[], source(pool/workspace), enabled |
| `GuardFinding` | severity, category, message, guardian |
| `GuardResult` | allowed, requires_approval, findings[], reason |
| `ApprovalRequest` | id, tool, args, findings[], status(pending/approved/rejected/expired), created_at |
| `CronJob` | id, name, cron, prompt, channel, agent_id, enabled, next_run |
| `PlanConfirmRequest` | thread_id, decision(approve/reject/edit), edited_todos? |

## 附2. API 契约总表（新增/变更）

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| POST | /api/v1/agent/chat | {message, thread_id?, agent_id?, source?} | ChatResponse |
| POST | /api/v1/agent/chat/stream | 同上 | SSE |
| POST | /api/v1/agent/plan/confirm | PlanConfirmRequest | {resumed, response} |
| GET | /api/v1/agents | - | WorkspaceInfo[] |
| POST | /api/v1/agents | {agent_id, config} | WorkspaceInfo |
| GET | /api/v1/agents/{agent_id} | - | WorkspaceInfo |
| DELETE | /api/v1/agents/{agent_id} | - | {deleted} |
| GET | /api/v1/skills?agent_id=default | - | {pool[], workspace[]} |
| POST | /api/v1/skills/install | {name, source_dir, overwrite?} | SkillInfo |
| POST | /api/v1/skills/{name}/enable?agent_id=... | {enabled} | {name, enabled} |
| POST | /api/v1/skills/{name}/add-to-workspace?agent_id=... | - | SkillInfo |
| POST | /api/v1/skills/scan | {path} | {safe, findings[]} |
| POST | /api/v1/skills/reload | {agent_id?} | {reloaded, agents[]} |
| GET | /api/v1/security/config | - | {level, enabled} |
| PUT | /api/v1/security/config | {level} | {level} |
| GET | /api/v1/security/approvals | - | {pending[]} |
| POST | /api/v1/security/approvals/resume | {thread_id, decision, approval_id?} | {resumed,...} |
| GET | /api/v1/providers | - | ProviderInfo[] |
| GET | /api/v1/providers/{name}/models | - | ModelInfo[] |
| POST | /api/v1/providers/{name}/check | - | {connected} |
| GET | /api/v1/tasks | status? | TaskResponse[] |
| POST | /api/v1/tasks | {title,prompt,auto_run?} | TaskResponse |
| GET | /api/v1/tasks/{task_id} | - | TaskResponse |
| POST | /api/v1/tasks/{task_id}/run | - | TaskResponse |
| POST | /api/v1/tasks/{task_id}/cancel | - | TaskResponse |
| GET/POST/DELETE | /api/v1/tasks/cron | CronJob | CronJob[] |
| GET/PUT | /api/v1/tasks/heartbeat | {enabled, interval, prompt} | config |
| GET | /api/v1/plugins | - | PluginInfo[] |
| POST | /api/v1/plugins/reload | - | {reloaded, plugins[]} |
| GET | /api/v1/commands | - | CommandInfo[] |
| GET | /api/v1/monitor/trace/{id}/timeline | - | TimelineEvent[] |
| GET | /api/v1/gateway/platforms | - | {platforms[]} |
| POST | /api/v1/gateway/{platform}/webhook | channel payload | GatewayWebhookResponse |
| GET | /api/v1/tools | - | {builtin, mcp, total} |
| GET | /api/v1/tools/mcp/servers | - | {servers} |
| POST | /api/v1/tools/mcp/reload | - | {status, tools, mcp_tools} |

## 附3. ToolGuard 决策矩阵

| Level \ Severity | INFO | LOW | MEDIUM | HIGH | CRITICAL |
|------------------|------|-----|--------|------|----------|
| OFF | 放行 | 放行 | 放行 | 放行 | 放行 |
| AUTO | 放行 | 放行 | 放行 | 放行* | 拒绝(denied) |
| SMART（默认） | 放行 | 放行 | 审批 | 审批 | 拒绝 |
| STRICT | 审批 | 审批 | 审批 | 审批 | 拒绝 |

\* AUTO 仅对显式 `guarded_tools` 审批。CRITICAL（如写 `.env`）始终拒绝。

## 附4. 每阶段验证命令速查

```bash
# 通用冒烟
.venv\Scripts\python -c "from app.main import app; print(app.title)"
.venv\Scripts\python -m pytest -q

# Phase1 就绪
curl http://localhost:8000/api/v1/monitor/health

# Phase2 计划确认
curl -X POST .../agent/chat -d '{"message":"/plan ..."}'
curl -X POST .../agent/plan/confirm -d '{"thread_id":"..","decision":"approve"}'

# Phase3 审批
curl .../security/approvals
curl -X POST .../security/approvals/resume -d '{"thread_id":"..","approval_id":"..","decision":"reject"}'

# 前端
cd frontend && npm run build
```

---

# Part H. 非功能性需求（NFR）

| 维度 | 指标 | 落地手段 |
|------|------|---------|
| 启动延迟 | Phase1 就绪 < 1s；Phase2 后台 < 15s | 两阶段启动，重资源后台加载 |
| 首字延迟 | SSE 首个 token < 2s（云模型） | 流式 `astream`，中间件不阻塞 |
| 并发会话 | 单实例 ≥ 50 并发 thread | 全异步；每 thread 独立 checkpointer 命名空间 |
| 渠道吞吐 | 每渠道队列 1000，背压丢弃最旧 | `asyncio.Queue(maxsize=1000)` |
| 工具超时 | 默认 60s，shell 120s | `execute` timeout 配置 |
| 内存占用 | 单 Workspace 常驻 < 200MB | 懒加载 + 空闲回收（LRU 逐出） |
| 可用性 | LLM/MCP 故障自恢复 | 指数退避重试 + MCP 三段恢复 |
| 数据持久 | trace/Cron/任务/审批/会话/领域数据均已具备 JSON/JSONL 落盘 | 后续可统一迁移 SQLite/Postgres |

**Workspace LRU 回收**：`MultiAgentManager` 维护 `last_access` 时间戳，超过 `AGENT_IDLE_TTL_MINUTES`（默认 30）且非 `default` 的 Workspace 释放 agent 实例（保留磁盘数据），下次访问重建。

---

# Part I. 鉴权与访问控制（规划中）

> QwenPaw 有渠道级访问控制（`get_access_control_store`）。本项目需在 API/Console/渠道三层设访问控制。
> 当前代码库已接入 API Token、内存限流、渠道白名单和 Console 登录；多用户 RBAC 仍列为后续可选增强。

## I.1 API 鉴权
- **模式**：Bearer Token（`API_TOKEN` 环境变量，单用户本地场景）+ 可选 JWT（多用户）。
- **实现**：FastAPI 依赖 `verify_token`（`Depends`）保护除 `/`, `/docs`, `/api/v1/monitor/health` 外的所有路由。
- **渠道 Webhook**：不走 Bearer，改用各渠道签名校验（钉钉 HMAC-SHA256、飞书 token、QQ secret）。

```python
# app/api/deps.py
from fastapi import Header, HTTPException
from app.core.config import settings
async def verify_token(authorization: str = Header(default="")):
    if not settings.api_token:            # 未配置则放行（本地开发）
        return
    if authorization != f"Bearer {settings.api_token}":
        raise HTTPException(401, "invalid token")
```

## I.2 渠道级访问白名单
- ✅ 每渠道可配 `allowed_users`（user_id 白名单）；非白名单消息拒绝并记 `GATEWAY_MESSAGE{action:"denied"}`。
- ✅ 配置存 `workspace/access_control.json`，每次校验从 JSON 读取，支持运行期热更新。
- ✅ 管理 API：`GET/PUT /api/v1/gateway/access-control`。

## I.3 Console 登录（可选，Phase 11 增强）
- ✅ 简单密码登录（`CONSOLE_PASSWORD`）→ 签发短期 JWT，前端存 localStorage，后端写入 HttpOnly cookie。
- ✅ 支持 `CONSOLE_JWT_SECRET` 和 `CONSOLE_JWT_TTL_MINUTES` 配置；未配置 `CONSOLE_PASSWORD` 时保持本地开放。
- 多用户 RBAC 列为未来扩展，本期不做。

---

# Part J. 数据持久化与存储演进

## J.1 存储分层（本期 → 演进）

| 数据 | 本期（MVP） | 演进（生产） |
|------|------------|-------------|
| 会话 checkpoint | `MemorySaver`（内存） | `SqliteSaver` / `PostgresSaver` |
| 任务 | JSON 文件 `workspace/tasks/task_history.json` | SQLite 表 + 分布式任务队列 |
| Cron | JSON 文件 `workspace/.cache/cron_jobs.json` | SQLite 表 |
| 审批队列 | 内存 | SQLite/JSONL + 审批历史 |
| 追踪事件 | 内存环形 + JSONL | SQLite / ClickHouse |
| 长期记忆 | AGENTS.md + Store | 向量库（可选 ReMe/pgvector） |
| 技能池 | 文件系统 | 文件系统 + 元数据 SQLite |
| 能力缓存 | JSON | JSON（够用） |

## J.2 持久化目录约定

```
workspace/
├── agents/{agent_id}/           # 每 Agent 独立根（FilesystemBackend）
│   ├── skills/                  # 工作区技能
│   ├── files/                   # Agent 工作区文件后端
│   └── AGENTS.md                # Agent 记忆
├── charts/  code/               # 全局产出（现有）
├── .cache/capabilities.json     # 能力缓存（已实现）
├── .cache/cron_jobs.json        # Cron 任务（已实现）
├── .cache/traces.jsonl          # Trace 事件（已实现）
├── .state/
│   ├── tasks.jsonl  approvals.jsonl
│   └── access_control.json
└── checkpoints.sqlite           # 演进：会话持久化
```

## J.3 SQLite 演进步骤（Phase 12 可选升级）
1. `pip install langgraph-checkpoint-sqlite aiosqlite`
2. 工厂 `checkpointer=AsyncSqliteSaver.from_conn_string("workspace/checkpoints.sqlite")`
3. 任务/审批/追踪迁移到 `sqlite3` 表（提供 `services/store/sqlite_store.py` 统一封装）。
4. 迁移脚本 `scripts/migrate_jsonl_to_sqlite.py`。

---

# Part K. 并发与韧性设计（详解）

## K.1 并发模型
- **全异步**：所有 IO（LLM、MCP、渠道、文件）走 `async`；CPU 密集（matplotlib 绘图）用 `asyncio.to_thread` 或进程池。
- **锁粒度**：`MultiAgentManager` 每 agent 一把 `asyncio.Lock`（仅初始化期持有）；审批队列用单锁 + `asyncio.Event`。
- **Plan 预锁**：借鉴 QwenPaw，`asyncio.gather` 并行工具中，规划/审批类工具在 `wrap_tool_call` 入口即判定，避免兄弟工具绕过门控（本项目中间件天然串行进入 `wrap_tool_call`，风险低，但需单测覆盖并行 tool_calls 场景）。

## K.2 LLM 重试（指数退避）
```python
# providers/retry.py
import asyncio, random
async def with_retry(fn, *, retries=3, base=1.0, factor=2.0):
    for i in range(retries + 1):
        try: return await fn()
        except Exception as e:
            if i == retries or not _is_retryable(e): raise
            await asyncio.sleep(base * (factor ** i) + random.uniform(0, 0.5))
def _is_retryable(e) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("rate limit","timeout","503","overloaded","connection"))
```

## K.3 MCP 三段恢复（对标 QwenPaw）
```
_reconnect(client) 成功? → 用原 client
        ↓ 失败
_rebuild(client, meta) → None? → 返回 None（禁用该 MCP）
        ↓ 重建成功
_reconnect(rebuilt) 成功? → 用 rebuilt
        ↓ 失败 → None
```
- `mcp_manager` 为每个 client 保存 `_rebuild_info{transport,name,command,args,env,url,headers}`。
- 工具调用捕获连接异常 → 触发恢复 → 恢复失败则该工具本轮返回错误 ToolMessage，不中断整个 agent。

## K.4 渠道背压
- 队列满 → 丢弃最旧 + 记 `WARN`；对用户回「系统繁忙，请稍后」。

## K.5 优雅关闭
- lifespan 退出：`scheduler.shutdown(wait=False)` → 取消进行中 task → `mcp_manager.disconnect()` → flush JSONL。

---

# Part L. 关键流程时序图与状态机

## L.1 Plan 门控状态机

```
        /plan 命令                write_todos 执行
  idle ───────────▶ planning ──────────────────▶ awaiting_confirm
   ▲                   │                                  │
   │                   │ 非规划工具→拦截                    │ interrupt() 挂起
   │                   ▼                                  ▼
   │              (拒绝执行)                    ┌── approve ──▶ executing ──┐
   │                                          ├── edit ─────▶ planning     │
   └────────────────── reject ◀───────────────┤                           │
                                              └───────────────────────────┘
                                                   执行完毕 → idle
```

## L.2 工具审批时序（ToolGuard + HITL）

```
LLM → tool_call(execute_shell) → wrap_tool_call
  → ToolGuardEngine.evaluate → requires_approval=True
  → emit APPROVAL_REQUESTED → interrupt({tool,args,findings})   [图挂起]
  → API GET /security/approvals 返回待审
  → 用户 POST /security/approvals/resume {thread_id, approval_id?, decision}
  → agent.ainvoke(Command(resume=decision))                     [图恢复]
  → decision==approve? handler(request)：ToolMessage("拒绝")
```

## L.3 渠道消息时序

```
钉钉/飞书 → Webhook → verify_signature → BaseChannel.parse_incoming
  → ChannelManager.enqueue → _process_batch
  → resolve_agent_id → MultiAgentManager.get_agent
  → agent.ainvoke(source="channel", trace_id=X)
  → MessageRenderer.render(result, channel_style)
  → BaseChannel.send_reply
```

## L.4 定时任务时序

```
APScheduler(cron) → trigger → emit CRON_TRIGGER
  → agent.ainvoke(prompt, source="cron")   [不写长期记忆]
  → render → channel.send_reply(target_channel)
```

---

# Part M. 可观测性度量目录

## M.1 结构化日志字段（统一）
`ts, level, event, trace_id, run_id, agent_id, thread_id, source, channel, tool, duration_ms, error`

## M.2 EventType 全集（含新增）
`AGENT_START/END, THINKING, TOOL_CALL/RESULT, SUBAGENT_START/END, TODO_UPDATE, ERROR, GATEWAY_MESSAGE, PLAN_CREATED/CONFIRMED, GUARD_BLOCK/APPROVED, APPROVAL_REQUESTED, SKILL_LOADED, CRON_TRIGGER, HEARTBEAT, MCP_RECOVER, PROVIDER_RETRY`

## M.3 指标（Metrics，OTel/Prometheus 可选）
| 指标 | 类型 | 说明 |
|------|------|------|
| `agent_runs_total{status}` | Counter | 运行次数 |
| `agent_run_duration_seconds` | Histogram | 端到端耗时 |
| `tool_calls_total{tool,status}` | Counter | 工具调用 |
| `guard_blocks_total{guardian}` | Counter | 拦截次数 |
| `approvals_pending` | Gauge | 待审数 |
| `llm_retries_total{provider}` | Counter | 重试 |
| `mcp_recover_total{result}` | Counter | MCP 恢复 |
| `channel_queue_depth{channel}` | Gauge | 队列深度 |

## M.4 Span 命名规范
`agent.run` → `agent.model_call` → `agent.tool.{name}` → `agent.subagent.{name}`；`trace_id` 作为 baggage 贯穿。

---

# Part N. 国际化与限流

## N.1 i18n（对标 QwenPaw 的 en/zh/ru/ja）
- 本期支持 `zh`/`en` 两语言（`LANG` 配置 + 请求级覆盖）。
- 安全提示、审批文案、命令帮助抽到 `app/i18n/{zh,en}.py` 字典；`t(key, lang)` 取值。
- Agent 系统提示按 `agent_config.language` 选择中/英基底。

## N.2 限流（Rate Limiting）
- **Provider 级**：✅ `PROVIDER_RATE_LIMIT_PER_MINUTE`，在 `ProviderManager.get_chat_model()` 入口按 `provider:model` 限制模型解析频率。
- **API 级**：✅ `API_RATE_LIMIT_PER_MINUTE`，按 token 优先、IP 兜底限流（可配）。
- **渠道级**：✅ `GATEWAY_RATE_LIMIT_PER_MINUTE`，按 `platform:user_id` 每分钟消息上限防刷，超限写入 `rate_limited` 审计。

---

# Part O. 子智能体 Prompt 目录（可直接使用）

> 放置于 `app/agents/subagents.py`，供 `create_deep_agent(subagents=...)`。

| 子智能体 | 职责 | 工具集 | 系统提示要点 |
|----------|------|--------|-------------|
| `researcher` | 调研/检索/汇总 | query_drilling_params, review_text, MCP 检索 | 「你是钻井调研专家，收集数据、交叉验证、结构化汇总，标注不确定性」 |
| `coder` | 代码/脚本 | generate_code, execute（受 Guard） | 「你是数据分析工程师，写可运行 Python/SQL，含类型注解与用例，遵循 PEP8」 |
| `chart-analyst` | 图表/可视化 | generate_chart, query_drilling_params | 「你是可视化专家，选合适图型，配色专业，输出文件路径与解读」 |
| `reviewer` | 审查/合规 | review_text, read_file | 「你是文档审查专家，检查完整性/合规/一致性，给出评分与整改清单」 |

**示例（reviewer 完整 system_prompt）**：
```text
你是 BoetClaw 的文档审查子智能体，专注钻井行业文档合规性审查。
职责：
1. 检查文档结构完整性（对照报告模板必备字段）
2. 核验数据一致性（前后数值、单位、量纲）
3. 识别 HSE/合规缺失项
4. 输出：总评分(0-100) + 问题清单(定位+严重度) + 整改建议
原则：仅审查不改写；不确定处标注「需人工复核」；用中文输出结构化结果。
```

---

# Part P. 渠道样例 Payload（解析测试基准）

## P.1 钉钉（text）
```json
{"msgtype":"text","text":{"content":"审查这份日报"},
 "senderStaffId":"u123","senderNick":"张三","conversationId":"c1","msgId":"m1"}
```

## P.2 飞书（im.message.receive_v1）
```json
{"header":{"event_type":"im.message.receive_v1"},
 "event":{"message":{"message_id":"om1","chat_id":"oc1","content":"{\"text\":\"生成报告\"}"},
          "sender":{"sender_id":{"open_id":"ou1"}}}}
```

## P.3 QQ / OneBot
```json
{"post_type":"message","message_type":"private","user_id":10001,
 "raw_message":"画个曲线","message_id":55,"sender":{"nickname":"李四"}}
```

## P.4 Telegram（webhook update）
```json
{"update_id":1,"message":{"message_id":9,"text":"/plan 汇总待办",
 "chat":{"id":42,"type":"private"},"from":{"id":42,"first_name":"Wang"}}}
```

> 每渠道 `test_channels.py` 用上述 payload 断言 `GatewayMessage` 字段。

---

# Part Q. 验收测试场景（Gherkin）

```gherkin
Feature: Plan 门控闭环
  Scenario: 用户发起规划并批准
    Given 服务已就绪且 agent_ready=true
    When 用户发送 "/plan 生成XX-1井完井报告并绘制曲线"
    Then 系统产生 PLAN_CREATED 事件
    And 运行进入 awaiting_confirm 挂起
    When 用户 POST /agent/plan/confirm decision=approve
    Then 运行进入 executing
    And 至少产生一次 generate_chart 的 TOOL_CALL

Feature: 工具安全审批
  Scenario: 拒绝高危 shell 命令
    Given TOOL_GUARD_LEVEL=smart
    When agent 尝试调用 execute_shell_command
    Then 产生 APPROVAL_REQUESTED 且运行挂起
    When 用户裁决 decision=reject
    Then 该工具不执行且返回 "[用户拒绝执行]"

Feature: 多智能体隔离
  Scenario: 文件互不可见
    Given 存在 agentA 与 agentB
    When agentA 写入 report.md
    Then agentB 执行 ls 看不到 report.md

Feature: 越权路径拦截
  Scenario: 写敏感文件被拒
    When agent 尝试 write_file 到 ".env"
    Then 产生 GUARD_BLOCK 且工具不执行
```

---

# Part R. 测试矩阵与 CI/CD

## R.1 测试矩阵

| 层级 | 范围 | 工具 | 覆盖目标 |
|------|------|------|---------|
| 单元 | Guardian/路由/技能解析/渠道解析/重试 | pytest | ≥ 70% 核心模块 |
| 集成 | 中间件栈/Plan/审批/MCP mock | pytest-asyncio | 关键路径全覆盖 |
| 契约 | API schema/OpenAPI | schemathesis（可选） | 全端点 |
| 前端 | 组件渲染/构建 | tsc + vitest（可选） | 构建必过 |
| 冒烟 | app 导入/健康检查 | pytest | 每次 CI |

## R.2 pytest 配置（`backend/pyproject.toml` 或 `pytest.ini`）
```ini
[pytest]
asyncio_mode = auto
addopts = -q --disable-warnings
testpaths = tests
```

## R.3 GitHub Actions（`.github/workflows/ci.yml`）
```yaml
name: CI
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && python -c "from app.main import app"
      - run: cd backend && pytest -q
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: cd frontend && npm ci && npm run build
```

## R.4 提交前钩子（可选 pre-commit）
`ruff`（lint+format）、`mypy`（类型）、`pytest -q`。

---

# Part S. 前端架构详解

## S.1 组件树
```
App
├── TopBar (AgentSwitcher, ThreadBadge, TraceBadge, ConnectionStatus)
├── MainChat
│   ├── ChatPanel (消息流 + 输入)
│   ├── PlanConfirm (interrupt=plan_confirm 时弹出)
│   └── ApprovalCard (interrupt=tool_approval 时弹出)
└── Sidebar
    ├── TaskMonitor (任务/Cron)
    ├── SidePanel (Trace/Tools/Stats 三 tab)
    ├── SkillsManager
    ├── ProviderSettings
    └── CronManager
```

## S.2 状态管理
- 轻量：React `useState` + `useContext`（`AgentContext` 存 activeAgentId/threadId/traceId）。
- SSE 事件经统一 `useAgentStream` hook 分发到消息流与追踪面板。
- 无需 Redux；跨组件共享用 Context + 自定义 hooks。

## S.3 SSE 事件处理约定
- 事件 `mode=messages` → 追加/更新助手消息。
- `data.type=plan_confirm` → 打开 `PlanConfirm`。
- `data.type=tool_approval` → 打开 `ApprovalCard`。
- `event: done` → 结束 loading。

## S.4 路由现状与目标

**现状（已审计）**：前端没有 `react-router` 路由表；开发态为 `/`，后端内置静态入口为 `/ui/`。功能通过组件状态和控制台 Tab 切换实现。

**Phase 14 目标路由**：
- `/chat`、`/chats`、`/chats/:threadId`
- `/tasks`、`/tasks/:taskId`
- `/agents`、`/agents/:agentId`
- `/trace/:traceId`
- `/settings/skills`、`/settings/providers`、`/settings/security`、`/settings/scheduler`、`/settings/plugins`、`/settings/mcp`
- `/channels`、`/channels/:platform`
- `/artifacts`、`/wells`（Phase 15/16）

这些路由必须和当前 `/api/v1/*` 后端接口对应，不能只做空壳页面。

---

# Part T. 钻井行业领域模型与技能（业务落地）

## T.1 领域数据模型
```python
# app/domain/models.py
class DrillingParam(BaseModel):
    well_id: str; depth: float
    wob: float; rpm: float; rop: float; flow_rate: float
    torque: float | None = None; spp: float | None = None  # 立管压力
class Formation(BaseModel):
    name: str; top_md: float; bottom_md: float; lithology: str
class DailyReport(BaseModel):
    well_id: str; date: str; depth_from: float; depth_to: float
    params: list[DrillingParam]; remarks: str; hse_notes: str
```

**当前状态**：以上模型尚未在代码中落地。现有领域能力主要来自 `review_text`、`generate_text`、`generate_chart`、`generate_code`、`query_drilling_params` 等内置工具，其中 `query_drilling_params` 返回模拟数据。真实井、井段、日报、LAS 文件与参数库转入 Phase 16。

## T.2 内置技能扩展清单（钻井）
| 技能 | 用途 |
|------|------|
| `drilling-report`（已有） | 日报/完井报告撰写与审查 |
| `chart-visualization`（已有） | 测井/参数曲线 |
| `code-generation`（已有） | LAS/WITSML 解析脚本 |
| `well-schematic`（新增） | 井身结构图生成（套管/井眼分段） |
| `las-parser`（新增） | LAS 测井文件解析与质量检查 |
| `hse-compliance`（新增） | HSE 合规检查清单 |
| `mud-report`（新增） | 钻井液性能报告 |

## T.3 领域工具扩展（Phase 4 附带）
- `parse_las(file)` → DataFrame（lasio）
- `well_schematic(sections)` → 井身结构 PNG
- `mud_property_check(data)` → 钻井液指标合规判定

## T.4 领域知识注入
- `AGENTS.md` 补充：钻井术语表、常见参数合理区间、报告模板规范、HSE 红线。

---

# Part U. 术语表

| 术语 | 含义 |
|------|------|
| DeepAgents | LangChain 的智能体 harness，含规划/文件系统/子智能体/HITL |
| Middleware | DeepAgents 能力叠加机制（钩子 before_model/wrap_tool_call 等） |
| HITL | Human-in-the-loop，人工介入审批（interrupt/resume） |
| Workspace | 单个智能体的隔离容器（配置/文件/记忆/技能/历史） |
| Skill Pool | 全局共享技能仓库 | 
| Effective Skills | 按 workspace+channel 解析出的实际生效技能集 |
| ToolGuard | 工具执行安全引擎（4 级策略 + Guardian） |
| Guardian | 具体安全检查器（规则/文件/Shell） |
| Provider | LLM 提供商抽象（OpenAI/Anthropic/Ollama…） |
| MCP | Model Context Protocol，外部工具服务器标准协议 |
| Heartbeat | 定时自检，用固定问题问 agent 并回发 |
| Trace/Run ID | 链路追踪标识，贯穿渠道→API→Agent→工具 |
| WOB/RPM/ROP/MD/TVD | 钻压/转速/机械钻速/测深/垂深 |

---

# Part V. 阶段依赖图与角色分工

## V.1 依赖图
```
Phase0
  └▶ Phase1 ─▶ Phase2 ─▶ Phase3   ← 关键路径（MVP / 里程碑 M-A）
                 │         │
                 │         ├▶ Phase4(技能) ─┐
                 │         ├▶ Phase5(多Agent)┤─▶ Phase8(渠道) ─▶ Phase9(定时)
                 │         ├▶ Phase6(Provider)┘
                 │         └▶ Phase7(记忆)
                 └───────────────────────────▶ Phase10(插件/命令)
Phase4..10 ─▶ Phase11(前端) ─▶ Phase12(可观测) ─▶ Phase13(部署)
```

## V.2 角色分工（若多人）
| 角色 | 负责阶段 |
|------|---------|
| 智能体/中间件工程师 | Phase 1,2,3,7,10 |
| 平台/后端工程师 | Phase 5,6,9,12,13 |
| 集成工程师 | Phase 4,8（技能/渠道） |
| 前端工程师 | Phase 11 |
| 领域专家（钻井） | Part T 技能内容与验收 |

## V.3 单人推进建议顺序
0→1→2→3（MVP 可演示）→ 5→4（多 Agent+技能）→ 6→7 → 8→9 → 10 → 11 → 12 → 13。

---

# 附录（补充）

## 附5. 完整配置项清单（config.py 目标字段）
| 组 | 字段 | 默认 |
|----|------|------|
| LLM | llm_provider, llm_model, *_api_key | openai/gpt-4o |
| Server | host, port, cors_origins, api_token | 0.0.0.0/8000/-/空 |
| 安全 | tool_guard_enabled, tool_guard_level, tool_guard_denied_tools, file_guard_deny_dirs | true/smart/-/.env,.git |
| 多Agent | default_agent_id, agents_root, agent_idle_ttl_minutes | default/./workspace/agents/30 |
| 定时 | heartbeat_enabled, heartbeat_interval_minutes, heartbeat_prompt | false/120/- |
| Provider | ollama_base_url, provider_rpm, provider_tpm | localhost:11434/-/- |
| i18n | lang | zh |
| 追踪 | langchain_tracing_v2, langchain_api_key, langchain_project | false/-/boetclaw |
| MCP | mcp_servers(JSON) | {} |
| 渠道 | 各平台 key/secret | 空 |

## 附6. 异常与错误码规范
| 场景 | HTTP | body |
|------|------|------|
| 未授权 | 401 | {detail:"invalid token"} |
| Agent 未就绪 | 503 | {detail:"agent not ready"} |
| 资源不存在 | 404 | {detail:"... not found"} |
| 参数校验失败 | 422 | pydantic 错误 |
| 工具被安全拦截 | 200(ToolMessage error) | 在会话内返回，不抛 HTTP |
| 内部错误 | 500 | {detail:str} + ERROR 事件 |

## 附7. Definition of Done（全局）
一个阶段"完成"须同时满足：
1. 代码可导入（冒烟通过）；2. 该阶段单测全绿；3. 该阶段验收命令输出符合预期；
4. 新增 API 出现在 `/docs`；5. 相关事件在 `/monitor/events` 可见；6. 不破坏既有阶段回归测试。

## 附8. 快速开始（更新后）
```bash
# 后端
cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # 填 API Key 与安全/多Agent 配置
.venv\Scripts\python run.py
# 前端
cd frontend && npm install && npm run dev
# 测试
cd backend && .venv\Scripts\python -m pytest -q
```

