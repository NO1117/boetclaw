"""DeepAgents agent factory and runtime."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

from app.core.config import settings
from app.core.execution_ref import parse_interrupt_result
from app.core.observability import (
    EventType,
    emit_event,
    get_logger,
    new_run_id,
    new_trace_id,
    run_id_var,
    trace_id_var,
)
from app.core.run_context import reset_run_context, set_run_context
from app.memory.plan_history_store import plan_history_store
from app.tools.builtin import get_builtin_tools
from app.tools.mcp_manager import mcp_manager

logger = get_logger("agent")

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


class AgentManager:
    """Creates and manages DeepAgents instances."""

    def __init__(self) -> None:
        self._agent: Any = None

    def _setup_env(self) -> None:
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

    def _build_subagents(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "researcher",
                "description": "钻井数据调研与文献检索子智能体",
                "system_prompt": "你是钻井行业调研专家，专注数据收集、参数分析和信息汇总。",
                "tools": get_builtin_tools(),
            },
            {
                "name": "coder",
                "description": "代码生成与数据分析脚本子智能体",
                "system_prompt": "你是钻井数据分析工程师，擅长 Python/SQL 脚本编写。",
                "tools": [t for t in get_builtin_tools() if t.name in ("generate_code", "query_drilling_params")],
            },
            {
                "name": "chart-analyst",
                "description": "图表生成与数据可视化子智能体",
                "system_prompt": "你是数据可视化专家，擅长钻井参数图表和测井曲线。",
                "tools": [t for t in get_builtin_tools() if t.name in ("generate_chart", "query_drilling_params")],
            },
        ]

    async def initialize(self) -> None:
        from app.core.agent_factory import BoetClawAgentFactory, setup_env
        from app.core.checkpoint import checkpoint_provider

        setup_env()
        settings.workspace_dir.mkdir(parents=True, exist_ok=True)
        checkpointer = await checkpoint_provider.get(settings.default_agent_id)

        memory_files = [str(settings.agents_md)] if settings.agents_md.exists() else None
        skills_path = [str(settings.skills_dir)] if settings.skills_dir.exists() else None

        self._agent = BoetClawAgentFactory.build(
            memory=memory_files,
            skills=skills_path,
            checkpointer=checkpointer,
        )
        logger.info("Agent initialized via factory", model=settings.model_string)

    async def reload_tools(self) -> None:
        await mcp_manager.reload()
        await self.initialize()

    @property
    def agent(self) -> Any:
        if self._agent is None:
            raise RuntimeError("Agent not initialized")
        return self._agent

    async def invoke(
        self,
        message: str,
        thread_id: str,
        *,
        source: str = "user",
        trace_id: str | None = None,
        run_id: str | None = None,
        task_id: str = "",
        agent_id: str = "default",
        well_id: str = "",
    ) -> dict[str, Any]:
        from app.memory.context_policy import normalize_source, should_persist_memory

        tid = trace_id or new_trace_id()
        rid = run_id or new_run_id()
        trace_id_var.set(tid)
        run_id_var.set(rid)
        context_tokens = set_run_context(
            task_id=task_id,
            agent_id=agent_id,
            thread_id=thread_id,
            well_id=well_id,
        )

        try:
            source = normalize_source(source)
            persist_memory = should_persist_memory(source)

            # /plan prefix -> enter planning phase
            plan_mode = message.strip().startswith("/plan")
            clean_msg = message.strip()[5:].strip() if plan_mode else message

            emit_event(
                EventType.AGENT_START,
                {
                    "message": clean_msg[:200],
                    "thread_id": thread_id,
                    "plan_mode": plan_mode,
                    "source": source,
                    "persist_memory": persist_memory,
                },
                trace_id=tid,
                run_id=rid,
            )

            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            state_in: dict[str, Any] = {"messages": [{"role": "user", "content": clean_msg}]}
            if plan_mode:
                state_in["plan_phase"] = "planning"

            result = await self.agent.ainvoke(state_in, config=config)

            has_interrupt = "__interrupt__" in result if isinstance(result, dict) else False
            envelope = parse_interrupt_result(
                result,
                agent_id=agent_id,
                thread_id=thread_id,
                checkpoint_ns="",
            )
            if has_interrupt and envelope is None:
                raise ValueError("LangGraph 中断缺少有效 id/type，无法安全恢复")
            interrupted = envelope is not None
            messages = result.get("messages", []) if isinstance(result, dict) else []
            last_msg = messages[-1] if messages else None
            content = getattr(last_msg, "content", str(last_msg)) if last_msg else ""

            todos = result.get("todos", []) if isinstance(result, dict) else []
            if envelope is not None:
                from app.services.execution_resume import graph_resume_adapter

                graph_resume_adapter.register(envelope.execution_ref, self.agent)
                if envelope.execution_ref.interrupt_type == "plan_confirm":
                    plan_history_store.record(
                        execution_ref=envelope.execution_ref,
                        action="created",
                        todos=todos,
                    )
                elif envelope.execution_ref.interrupt_type == "tool_approval":
                    from app.security.approval import approval_service

                    approval_id = envelope.payload.get("approval_id")
                    if not isinstance(approval_id, str) or not approval_service.bind_execution_ref(
                        approval_id, envelope.execution_ref
                    ):
                        raise ValueError("工具审批中断无法绑定审批记录")

            if not interrupted:
                emit_event(
                    EventType.MEMORY_PERSIST if persist_memory else EventType.MEMORY_SKIP,
                    {"thread_id": thread_id, "source": source},
                    trace_id=tid,
                    run_id=rid,
                )

            emit_event(
                EventType.AGENT_END,
                {"thread_id": thread_id, "response_length": len(str(content)), "interrupted": interrupted},
                trace_id=tid,
                run_id=rid,
            )

            return {
                "thread_id": thread_id,
                "trace_id": tid,
                "run_id": rid,
                "agent_id": agent_id,
                "response": content,
                "todos": todos,
                "message_count": len(messages),
                "interrupted": interrupted,
                "execution_ref": envelope.execution_ref.model_dump() if envelope else None,
                "payload": envelope.payload if envelope else None,
                "source": source,
            }
        finally:
            reset_run_context(context_tokens)

    async def confirm_plan(
        self,
        thread_id: str,
        decision: str,
        edited_todos: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for one-cycle default-agent thread-only requests."""
        from app.services.plan_resume import plan_resume_service

        return await plan_resume_service.resume(
            thread_id=thread_id,
            decision=decision,
            edited_todos=edited_todos,
        )

    async def stream(
        self,
        message: str,
        thread_id: str,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        agent_id: str = "default",
        well_id: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        tid = trace_id or new_trace_id()
        rid = run_id or new_run_id()
        trace_id_var.set(tid)
        run_id_var.set(rid)
        context_tokens = set_run_context(
            agent_id=agent_id,
            thread_id=thread_id,
            well_id=well_id,
        )

        try:
            emit_event(
                EventType.AGENT_START,
                {"message": message[:200], "thread_id": thread_id},
                trace_id=tid,
                run_id=rid,
            )

            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

            async for event in self.agent.astream(
                {"messages": [{"role": "user", "content": message}]},
                config=config,
                stream_mode=["messages", "updates"],
                subgraphs=True,
            ):
                yield self._normalize_stream_event(event, tid, rid)

            emit_event(EventType.AGENT_END, {"thread_id": thread_id}, trace_id=tid, run_id=rid)
        finally:
            reset_run_context(context_tokens)

    def _normalize_stream_event(
        self, event: Any, trace_id: str, run_id: str
    ) -> dict[str, Any]:
        """Normalize LangGraph stream events for frontend consumption."""
        payload: dict[str, Any] = {"trace_id": trace_id, "run_id": run_id}

        if isinstance(event, tuple):
            if len(event) == 3:
                namespace, mode, data = event
                payload["namespace"] = str(namespace)
                payload["mode"] = mode
                payload["data"] = self._serialize_data(data)
            elif len(event) == 2:
                mode, data = event
                payload["mode"] = mode
                payload["data"] = self._serialize_data(data)
            else:
                payload["raw"] = str(event)
        else:
            payload["data"] = self._serialize_data(event)

        if payload.get("mode") == "updates":
            data = payload.get("data", {})
            if isinstance(data, dict):
                if "todos" in data:
                    emit_event(
                        EventType.TODO_UPDATE,
                        {"todos": data["todos"]},
                        trace_id=trace_id,
                        run_id=run_id,
                    )
                for key in data:
                    if "tool" in key.lower() or "Tool" in key:
                        emit_event(
                            EventType.TOOL_CALL,
                            {"node": key, "data": str(data[key])[:500]},
                            trace_id=trace_id,
                            run_id=run_id,
                        )

        return payload

    def _serialize_data(self, data: Any) -> Any:
        if hasattr(data, "content"):
            return {"type": "message", "content": data.content, "role": getattr(data, "type", "ai")}
        if isinstance(data, dict):
            serialized = {}
            for k, v in data.items():
                if hasattr(v, "content"):
                    serialized[k] = {"content": v.content}
                elif isinstance(v, list):
                    serialized[k] = [
                        {"content": i.content} if hasattr(i, "content") else str(i) for i in v
                    ]
                else:
                    serialized[k] = str(v)[:1000]
            return serialized
        return str(data)[:2000]

    def list_tools(self) -> list[dict[str, Any]]:
        tools = []
        for t in get_builtin_tools():
            tools.append({"name": t.name, "description": t.description, "source": "builtin"})
        tools.extend(mcp_manager.list_tools())
        return tools


agent_manager = AgentManager()
