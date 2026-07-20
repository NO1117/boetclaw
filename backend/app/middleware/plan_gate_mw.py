"""Plan-gate middleware: enforces plan -> confirm -> execute flow.

Mirrors QwenPaw's plan gate using DeepAgents' built-in `write_todos` tool and
LangGraph `interrupt()` for human confirmation.
"""

from __future__ import annotations

from typing import Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.observability import EventType, emit_event

PLAN_TOOLS = {"write_todos"}


class PlanGateMiddleware(AgentMiddleware):
    """Gate tool execution while the agent is in a planning phase.

    - phase == "planning": only PLAN_TOOLS may execute; others are blocked.
    - executing `write_todos` triggers an interrupt for user confirmation.
    """

    name = "boetclaw_plan_gate"

    def _phase(self, request: ToolCallRequest) -> str:
        state = getattr(request, "state", None)
        if isinstance(state, dict):
            return state.get("plan_phase", "idle") or "idle"
        return "idle"

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], "ToolMessage | Command"],
    ) -> "ToolMessage | Command":
        tool = request.tool_call.get("name", "")
        phase = self._phase(request)
        tool_call_id = request.tool_call.get("id", "")

        # In planning phase, block any non-planning tool.
        if phase == "planning" and tool not in PLAN_TOOLS:
            emit_event(EventType.THINKING, {"plan_gate": "blocked", "tool": tool})
            return ToolMessage(
                content="当前处于规划阶段，请先使用 write_todos 制定完整计划，经用户确认后再执行其他工具。",
                tool_call_id=tool_call_id,
                status="error",
            )

        # When the plan is written, pause for confirmation.
        if tool in PLAN_TOOLS and phase in ("planning", "idle"):
            result = handler(request)
            emit_event(EventType.PLAN_CREATED, {"tool": tool, "args": str(request.tool_call.get("args"))[:800]})
            from langgraph.types import interrupt

            decision = interrupt(
                {"type": "plan_confirm", "todos": request.tool_call.get("args", {})}
            )
            emit_event(EventType.PLAN_CONFIRMED, {"decision": str(decision)})
            return result

        return handler(request)
