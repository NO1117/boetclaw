"""Shared agent run helpers (used by single-agent manager and multi-agent workspaces)."""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.core.execution_ref import parse_interrupt_result

from app.core.observability import (
    EventType,
    emit_event,
    new_run_id,
    new_trace_id,
    run_id_var,
    trace_id_var,
)
from app.core.run_context import reset_run_context, set_run_context


async def invoke_agent(
    agent: Any,
    message: str,
    thread_id: str,
    *,
    agent_id: str = "default",
    source: str = "user",
    trace_id: str | None = None,
    run_id: str | None = None,
    task_id: str = "",
    well_id: str = "",
    user_content: str | list[Any] | None = None,
    model_string: str | None = None,
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

    snapshot_token = None
    try:
        from app.agents.profile.models import EffectiveAgentConfig
        from app.agents.profile.service import profile_service
        from app.agents.profile.snapshot import reset_run_snapshot, set_run_snapshot

        effective = profile_service.effective_for_agent(agent_id)
        snapshot_token = set_run_snapshot(EffectiveAgentConfig.model_validate(effective).model_dump())
    except Exception:  # noqa: BLE001
        snapshot_token = None

    try:
        source = normalize_source(source)
        persist_memory = should_persist_memory(source)

        plan_mode = message.strip().startswith("/plan")
        clean_msg = message.strip()[5:].strip() if plan_mode else message

        emit_event(
            EventType.AGENT_START,
            {
                "message": clean_msg[:200],
                "thread_id": thread_id,
                "agent_id": agent_id,
                "plan_mode": plan_mode,
                "source": source,
                "persist_memory": persist_memory,
            },
            trace_id=tid,
            run_id=rid,
        )

        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        content = user_content if user_content is not None else clean_msg
        if plan_mode:
            content = clean_msg
        state_in: dict[str, Any] = {"messages": [{"role": "user", "content": content}]}
        if plan_mode:
            state_in["plan_phase"] = "planning"

        invoke_agent = agent
        graph_cache_hit: bool | None = None
        graph_cache_build_ms: float | None = None
        effective_provider: str | None = None
        effective_model: str | None = None
        if model_string:
            from app.agents.resolver import build_agent_graph_with_model
            from app.providers.manager import provider_manager

            effective_provider, effective_model = provider_manager.parse_model_string(model_string)
            invoke_agent, graph_cache_hit, graph_cache_build_ms = await build_agent_graph_with_model(
                agent_id, model_string
            )
            config = {
                **config,
                "configurable": {
                    **config.get("configurable", {}),
                    "model_string": model_string,
                },
            }

        from app.services.run_metrics import run_metrics_tracker

        run_metrics_tracker.start(
            trace_id=tid,
            run_id=rid,
            agent_id=agent_id,
            provider=effective_provider,
            model=effective_model,
            graph_cache_hit=graph_cache_hit,
            graph_cache_build_ms=graph_cache_build_ms,
        )

        result = await invoke_agent.ainvoke(state_in, config=config)

        finalized = _finalize_agent_result(
            invoke_agent,
            result,
            agent_id=agent_id,
            thread_id=thread_id,
        )
        interrupted = finalized["interrupted"]
        content = finalized["response"]
        todos = finalized["todos"]

        if not interrupted:
            emit_event(
                EventType.MEMORY_PERSIST if persist_memory else EventType.MEMORY_SKIP,
                {"thread_id": thread_id, "agent_id": agent_id, "source": source},
                trace_id=tid,
                run_id=rid,
            )

        messages = result.get("messages", []) if isinstance(result, dict) else []
        from app.services.run_metrics import extract_usage_from_messages, run_metrics_tracker

        usage = extract_usage_from_messages(messages)
        metrics = run_metrics_tracker.complete(
            tid,
            usage=usage,
            provider=effective_provider,
            model=effective_model,
            status="completed" if not interrupted else "interrupted",
        )

        emit_event(
            EventType.AGENT_END,
            {"thread_id": thread_id, "agent_id": agent_id, "interrupted": interrupted},
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
            "message_count": finalized["message_count"],
            "interrupted": interrupted,
            "execution_ref": finalized["execution_ref"],
            "payload": finalized["payload"],
            "source": source,
            "run_metrics": metrics.to_dict() if metrics else None,
        }
    finally:
        if snapshot_token is not None:
            from app.agents.profile.snapshot import reset_run_snapshot

            reset_run_snapshot(snapshot_token)
        reset_run_context(context_tokens)


def _finalize_agent_result(
    agent: Any,
    result: Any,
    *,
    agent_id: str,
    thread_id: str,
    streamed_content: str = "",
) -> dict[str, Any]:
    has_interrupt = "__interrupt__" in result if isinstance(result, dict) else False
    envelope = parse_interrupt_result(
        result,
        agent_id=agent_id,
        thread_id=thread_id,
        checkpoint_ns="",
    )
    if has_interrupt and envelope is None:
        raise ValueError("LangGraph 中断缺少有效 id/type，无法安全恢复")

    messages = result.get("messages", []) if isinstance(result, dict) else []
    last_msg = messages[-1] if messages else None
    content = streamed_content or (
        getattr(last_msg, "content", str(last_msg)) if last_msg else ""
    )
    todos = result.get("todos", []) if isinstance(result, dict) else []

    if envelope is not None:
        from app.services.execution_resume import graph_resume_adapter

        graph_resume_adapter.register(envelope.execution_ref, agent)
        if envelope.execution_ref.interrupt_type == "plan_confirm":
            from app.memory.plan_history_store import plan_history_store

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

    return {
        "response": content,
        "todos": todos,
        "message_count": len(messages),
        "interrupted": envelope is not None,
        "execution_ref": envelope.execution_ref.model_dump() if envelope else None,
        "payload": envelope.payload if envelope else None,
    }


def _merge_stream_update(result: dict[str, Any], data: Any) -> None:
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if key == "__interrupt__":
            result[key] = value
        elif isinstance(value, dict):
            _merge_stream_update(result, value)
        elif key in {"messages", "todos", "plan_phase"}:
            result[key] = value


def _stream_message(data: Any) -> Any:
    if isinstance(data, tuple) and data:
        return data[0]
    return data


def _serialize_stream_data(data: Any) -> Any:
    message = _stream_message(data)
    if hasattr(message, "content"):
        return {
            "type": "message",
            "content": message.content,
            "role": getattr(message, "type", "ai"),
        }
    if isinstance(data, dict):
        serialized: dict[str, Any] = {}
        for key, value in data.items():
            if hasattr(value, "content"):
                serialized[key] = {"content": value.content}
            elif isinstance(value, (list, tuple)):
                serialized[key] = [
                    {"content": item.content} if hasattr(item, "content") else str(item)
                    for item in value
                ]
            elif isinstance(value, dict):
                serialized[key] = _serialize_stream_data(value)
            else:
                serialized[key] = str(value)[:1000]
        return serialized
    return str(data)[:2000]


async def stream_agent(
    agent: Any,
    message: str,
    thread_id: str,
    *,
    agent_id: str = "default",
    source: str = "user",
    trace_id: str | None = None,
    run_id: str | None = None,
    user_content: str | list[Any] | None = None,
    model_string: str | None = None,
    attachment_count: int = 0,
    retrieval_hits: int = 0,
) -> AsyncIterator[dict[str, Any]]:
    """Stream one Agent run and finish with the same result contract as invoke_agent."""
    from app.memory.context_policy import normalize_source, should_persist_memory

    tid = trace_id or new_trace_id()
    rid = run_id or new_run_id()
    trace_id_var.set(tid)
    run_id_var.set(rid)
    context_tokens = set_run_context(
        agent_id=agent_id,
        thread_id=thread_id,
    )
    snapshot_token = None
    try:
        from app.agents.profile.models import EffectiveAgentConfig
        from app.agents.profile.service import profile_service
        from app.agents.profile.snapshot import set_run_snapshot

        effective = profile_service.effective_for_agent(agent_id)
        snapshot_token = set_run_snapshot(EffectiveAgentConfig.model_validate(effective).model_dump())
    except Exception:  # noqa: BLE001
        snapshot_token = None
    source = normalize_source(source)
    persist_memory = should_persist_memory(source)
    plan_mode = message.strip().startswith("/plan")
    clean_msg = message.strip()[5:].strip() if plan_mode else message
    result: dict[str, Any] = {}
    content_parts: list[str] = []

    try:
        emit_event(
            EventType.AGENT_START,
            {
                "message": clean_msg[:200],
                "thread_id": thread_id,
                "agent_id": agent_id,
                "plan_mode": plan_mode,
                "source": source,
                "persist_memory": persist_memory,
            },
            trace_id=tid,
            run_id=rid,
        )
        content = user_content if user_content is not None else clean_msg
        if plan_mode:
            content = clean_msg
        state_in: dict[str, Any] = {"messages": [{"role": "user", "content": content}]}
        if plan_mode:
            state_in["plan_phase"] = "planning"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

        stream_agent = agent
        graph_cache_hit: bool | None = None
        graph_cache_build_ms: float | None = None
        effective_provider: str | None = None
        effective_model: str | None = None
        if model_string:
            from app.agents.resolver import build_agent_graph_with_model
            from app.providers.manager import provider_manager

            effective_provider, effective_model = provider_manager.parse_model_string(model_string)
            stream_agent, graph_cache_hit, graph_cache_build_ms = await build_agent_graph_with_model(
                agent_id, model_string
            )
            config = {
                **config,
                "configurable": {
                    **config.get("configurable", {}),
                    "model_string": model_string,
                },
            }

        from app.services.run_metrics import run_metrics_tracker

        run_metrics_tracker.start(
            trace_id=tid,
            run_id=rid,
            agent_id=agent_id,
            provider=effective_provider,
            model=effective_model,
            attachment_count=attachment_count,
            retrieval_hits=retrieval_hits,
            graph_cache_hit=graph_cache_hit,
            graph_cache_build_ms=graph_cache_build_ms,
        )
        first_token_recorded = False

        async for raw_event in stream_agent.astream(
            state_in,
            config=config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            namespace = ""
            if isinstance(raw_event, tuple) and len(raw_event) == 3:
                namespace, mode, data = raw_event
            elif isinstance(raw_event, tuple) and len(raw_event) == 2:
                mode, data = raw_event
            else:
                mode, data = "updates", raw_event

            if mode == "messages":
                chunk = _stream_message(data)
                chunk_content = getattr(chunk, "content", "")
                if isinstance(chunk_content, str) and chunk_content:
                    if not first_token_recorded:
                        run_metrics_tracker.record_first_token(tid)
                        first_token_recorded = True
                    content_parts.append(chunk_content)
            elif mode == "updates":
                _merge_stream_update(result, data)

            yield {
                "kind": "update",
                "trace_id": tid,
                "run_id": rid,
                "mode": mode,
                "namespace": str(namespace),
                "data": _serialize_stream_data(data),
            }

        finalized = _finalize_agent_result(
            stream_agent,
            result,
            agent_id=agent_id,
            thread_id=thread_id,
            streamed_content="".join(content_parts),
        )
        if not finalized["interrupted"]:
            emit_event(
                EventType.MEMORY_PERSIST if persist_memory else EventType.MEMORY_SKIP,
                {"thread_id": thread_id, "agent_id": agent_id, "source": source},
                trace_id=tid,
                run_id=rid,
            )

        messages = result.get("messages", []) if isinstance(result, dict) else []
        from app.services.run_metrics import extract_usage_from_messages

        usage = extract_usage_from_messages(messages)
        metrics = run_metrics_tracker.complete(
            tid,
            usage=usage,
            provider=effective_provider,
            model=effective_model,
            status="completed" if not finalized["interrupted"] else "interrupted",
        )

        emit_event(
            EventType.AGENT_END,
            {"thread_id": thread_id, "agent_id": agent_id, "interrupted": finalized["interrupted"]},
            trace_id=tid,
            run_id=rid,
        )
        yield {
            "kind": "result",
            "trace_id": tid,
            "run_id": rid,
            **finalized,
            "source": source,
            "run_metrics": metrics.to_dict() if metrics else None,
        }
    finally:
        if snapshot_token is not None:
            from app.agents.profile.snapshot import reset_run_snapshot

            reset_run_snapshot(snapshot_token)
        reset_run_context(context_tokens)


async def confirm_agent(agent: Any, thread_id: str, decision: str) -> dict[str, Any]:
    from langgraph.types import Command

    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke(Command(resume=decision), config=config)
    messages = result.get("messages", []) if isinstance(result, dict) else []
    last_msg = messages[-1] if messages else None
    content = getattr(last_msg, "content", str(last_msg)) if last_msg else ""
    return {
        "thread_id": thread_id,
        "resumed": True,
        "decision": decision,
        "response": content,
        "message_count": len(messages),
    }
