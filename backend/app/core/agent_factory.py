"""Central factory for building DeepAgents instances with the BoetClaw stack."""

from __future__ import annotations

import os
from typing import Any

from app.core.config import settings
from app.core.observability import get_logger
from app.middleware.observability_mw import ObservabilityMiddleware
from app.tools.builtin import get_builtin_tools
from app.tools.mcp_manager import mcp_manager

logger = get_logger("agent_factory")

SYSTEM_PROMPT = """你是 BoetClaw 智能助手，面向钻井行业（但不限于），具备类似 Cursor/Trae 的自主规划与执行能力。

## 工作模式

1. **规划**：收到复杂任务时，先用 write_todos 制定分步计划
2. **执行**：按计划调用工具，必要时委派子智能体处理专项任务
3. **汇报**：完成后汇总结果，展示关键产出（文件路径、图表 URL 等）

## 可用能力

- review_text: 文本审查
- generate_text: 专业文档生成
- generate_chart: 数据图表可视化
- generate_code: 代码生成
- query_drilling_params: 钻井参数查询
- 文件系统工具: 读写工作区文件
- 子智能体: 委派 research/code/chart 专项任务

## 注意事项

- 使用中文回复
- 图表和代码生成后告知用户文件路径
- 不确定时主动询问用户
"""

DEFAULT_INTERRUPT = {"write_file": True, "edit_file": True, "delete": True}


def setup_env() -> None:
    """Export API keys and tracing config to the process environment."""
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    if settings.google_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    if settings.langchain_tracing_v2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project


def build_default_subagents() -> list[dict[str, Any]]:
    tools = get_builtin_tools()
    return [
        {
            "name": "researcher",
            "description": "钻井数据调研与文献检索子智能体",
            "system_prompt": "你是钻井行业调研专家，专注数据收集、参数分析和信息汇总。",
            "tools": tools,
        },
        {
            "name": "coder",
            "description": "代码生成与数据分析脚本子智能体",
            "system_prompt": "你是钻井数据分析工程师，擅长 Python/SQL 脚本编写，遵循 PEP8 并附类型注解。",
            "tools": [t for t in tools if t.name in ("generate_code", "query_drilling_params")],
        },
        {
            "name": "chart-analyst",
            "description": "图表生成与数据可视化子智能体",
            "system_prompt": "你是数据可视化专家，擅长钻井参数图表和测井曲线，输出文件路径与解读。",
            "tools": [t for t in tools if t.name in ("generate_chart", "query_drilling_params")],
        },
        {
            "name": "reviewer",
            "description": "文档审查与合规子智能体",
            "system_prompt": (
                "你是 BoetClaw 的文档审查子智能体，专注钻井行业文档合规性审查。"
                "检查结构完整性、数据一致性、HSE/合规缺失；输出总评分(0-100)+问题清单+整改建议；"
                "仅审查不改写，不确定处标注需人工复核，用中文结构化输出。"
            ),
            "tools": [t for t in tools if t.name in ("review_text",)],
        },
    ]


def _resolve_model() -> Any:
    """Resolve a chat model instance via ProviderManager when the provider is configured.

    Falls back to the plain `provider:model` string (deepagents/init_chat_model
    resolves it lazily) so tests and unconfigured environments still build.
    """
    try:
        from app.providers.manager import provider_manager

        provider_name, _ = provider_manager.parse_model_string(settings.model_string)
        provider = provider_manager.get(provider_name)
        if provider.is_configured():
            return provider_manager.get_chat_model(settings.model_string)
    except Exception as exc:  # noqa: BLE001
        logger.warning("model_resolve_fallback", error=str(exc))
    return settings.model_string


def _build_summarization_mw(model: Any, backend: Any) -> Any:
    """Construct DeepAgents SummarizationMiddleware; None on any failure.

    Requires a backend to persist condensed history. Falls back to a
    FilesystemBackend rooted at the workspace when none is supplied.
    """
    try:
        from deepagents.middleware import SummarizationMiddleware

        summ_backend = backend
        if summ_backend is None:
            from deepagents.backends import FilesystemBackend

            settings.workspace_dir.mkdir(parents=True, exist_ok=True)
            summ_backend = FilesystemBackend(root_dir=str(settings.workspace_dir))

        return SummarizationMiddleware(
            model=model,
            backend=summ_backend,
            keep=("messages", settings.context_keep_messages),
            trim_tokens_to_summarize=settings.context_trigger_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("summarization_mw_disabled", error=str(exc))
        return None


class BoetClawAgentFactory:
    """Builds `create_deep_agent` instances with a consistent middleware stack."""

    @staticmethod
    def build(
        *,
        model: Any = None,
        tools: list | None = None,
        subagents: list | None = None,
        skills: list[str] | None = None,
        memory: list[str] | None = None,
        backend: Any = None,
        checkpointer: Any = None,
        state_schema: Any = None,
        interrupt_on: dict | None = None,
        extra_middleware: list | None = None,
        enable_plan_gate: bool = True,
        enable_tool_guard: bool = True,
        enable_summarization: bool | None = None,
        store: Any = None,
    ) -> Any:
        from deepagents import create_deep_agent

        from app.middleware.plan_gate_mw import PlanGateMiddleware

        base_tools = tools if tools is not None else get_builtin_tools()

        from app.plugins.registry import plugin_registry

        all_tools = list(base_tools) + list(mcp_manager.tools) + list(plugin_registry.enabled_tools())

        from app.middleware.tool_guard_mw import ToolGuardMiddleware

        resolved_model = model if model is not None else _resolve_model()

        # Fixed order: Observability -> PlanGate -> ToolGuard -> Summarization -> extras
        middleware: list = [ObservabilityMiddleware()]
        if enable_plan_gate:
            middleware.append(PlanGateMiddleware())
            if state_schema is None:
                from app.agents.state import BoetClawState

                state_schema = BoetClawState
        if enable_tool_guard:
            middleware.append(ToolGuardMiddleware())

        summ_on = enable_summarization if enable_summarization is not None else settings.context_summarization_enabled
        if summ_on:
            summ_mw = _build_summarization_mw(resolved_model, backend)
            if summ_mw is not None:
                middleware.append(summ_mw)
        if extra_middleware:
            middleware.extend(extra_middleware)

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "tools": all_tools,
            "system_prompt": SYSTEM_PROMPT,
            "subagents": subagents if subagents is not None else build_default_subagents(),
            "middleware": middleware,
            "interrupt_on": interrupt_on if interrupt_on is not None else DEFAULT_INTERRUPT,
        }
        if skills:
            kwargs["skills"] = skills
        if memory:
            kwargs["memory"] = memory
        if backend is not None:
            kwargs["backend"] = backend
        if checkpointer is not None:
            kwargs["checkpointer"] = checkpointer
        if state_schema is not None:
            kwargs["state_schema"] = state_schema
        if store is not None:
            kwargs["store"] = store

        agent = create_deep_agent(**kwargs)
        logger.info(
            "agent_built",
            model=str(kwargs["model"]),
            tools=len(all_tools),
            middleware=[m.name for m in middleware],
        )
        return agent
