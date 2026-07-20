# BoetClaw 架构说明

BoetClaw 是面向钻井行业的 DeepAgents 智能体系统，后端以 FastAPI 为入口，DeepAgents/LangGraph 负责规划、执行、工具调用、技能加载与中断恢复，前端以 React 控制台呈现对话、计划确认、审批、技能、模型、调度和链路追踪。

## 运行时分层

```text
React Console
  ├─ Chat / PlanConfirm / ApprovalCard
  ├─ Skills / Providers / Cron / Plugins
  └─ Trace Timeline
        │
FastAPI REST + SSE
        │
BoetClaw Agent Factory
  ├─ ObservabilityMiddleware
  ├─ PlanGateMiddleware
  ├─ ToolGuardMiddleware
  ├─ SummarizationMiddleware (optional)
  ├─ Skills / Plugins / MCP tools
  └─ FilesystemBackend / Memory / Store
        │
DeepAgents + LangGraph
```

## 核心模块

- `backend/app/core/agent_factory.py`：统一构建 DeepAgent，注入中间件、工具、技能、后端和 checkpointer。
- `backend/app/middleware/`：规划门控、工具安全、可观测性。
- `backend/app/security/`：ToolGuard 安全引擎、guardian 规则、审批服务。
- `backend/app/skills_system/`：全局技能池、工作区技能副本、安全扫描。
- `backend/app/agents/`：多智能体工作区、懒加载、隔离文件系统。
- `backend/app/providers/`：OpenAI/Anthropic/Ollama provider 抽象。
- `backend/app/services/gateway/`：钉钉、飞书、QQ、Telegram 渠道抽象与队列。
- `backend/app/services/cron_service.py`：APScheduler 定时任务。
- `backend/app/plugins/` 和 `backend/app/commands/`：安全默认插件加载与 `/slash` 命令。
- `backend/app/core/observability.py`：TraceStore、事件、JSONL 持久化。

## 生命周期

1. `phase1_fast`：创建 workspace，注册渠道，启动渠道消费者，扫描插件（只加载启用项）。
2. `phase2_background`：连接 MCP，初始化 agent，启动 Cron/Heartbeat。
3. `lifespan` 关闭：停止 Cron、渠道消费者、MCP 连接。

## 数据目录

- `backend/workspace/`：运行产物、图表、代码、trace JSONL、cron 配置。
- `backend/workspace/agents/{agent_id}/`：每个智能体的独立文件与技能副本。
- `backend/skills/`：全局技能池。
- `backend/plugins_ext/`：外部插件目录，默认不启用。

## 部署拓扑

Docker Compose 默认包含：

- `backend`：FastAPI + DeepAgents，端口 `8000`。
- `frontend`：Nginx 静态前端 + `/api` 反向代理，端口 `5173`。
- `ollama`：可选 profile，本地模型服务，端口 `11434`。
