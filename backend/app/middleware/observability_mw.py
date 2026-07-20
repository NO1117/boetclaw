"""Observability middleware: injects trace events into the agent loop."""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.observability import EventType, emit_event


class ObservabilityMiddleware(AgentMiddleware):
    """Emits trace events for model reasoning and tool execution."""

    name = "boetclaw_observability"

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        msgs = state.get("messages", []) if isinstance(state, dict) else []
        emit_event(EventType.THINKING, {"phase": "before_model", "msg_count": len(msgs)})
        return None

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        msgs = state.get("messages", []) if isinstance(state, dict) else []
        last = msgs[-1] if msgs else None
        tool_calls = getattr(last, "tool_calls", None) or []
        for tc in tool_calls:
            emit_event(
                EventType.TOOL_CALL,
                {"tool": tc.get("name"), "args": str(tc.get("args"))[:500], "stage": "planned"},
            )
        return None

    def wrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], "ToolMessage | Command"]
    ) -> "ToolMessage | Command":
        name = request.tool_call.get("name", "?")
        emit_event(EventType.TOOL_CALL, {"tool": name, "stage": "invoke"})
        result = handler(request)
        emit_event(EventType.TOOL_RESULT, {"tool": name, "stage": "done"})
        return result
