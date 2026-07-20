"""Tool guard middleware: intercepts tool calls, enforces security policy + HITL."""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.observability import EventType, emit_event
from app.i18n import t


class ToolGuardMiddleware(AgentMiddleware):
    name = "boetclaw_tool_guard"

    def __init__(self, approvals: Any = None) -> None:
        self._engine: Any = None
        self._approvals = approvals

    def _lazy_engine(self) -> Any:
        if self._engine is None:
            from app.security.engine import get_guard_engine

            self._engine = get_guard_engine()
        return self._engine

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], "ToolMessage | Command"],
    ) -> "ToolMessage | Command":
        engine = self._lazy_engine()
        name = request.tool_call.get("name", "")
        args = request.tool_call.get("args", {}) or {}
        tool_call_id = request.tool_call.get("id", "")

        result = engine.evaluate(name, args)

        if not result.allowed:
            emit_event(EventType.GUARD_BLOCK, {"tool": name, "reason": result.reason})
            return ToolMessage(
                content=t("security.blocked", reason=result.reason),
                tool_call_id=tool_call_id,
                status="error",
            )

        if result.requires_approval:
            findings = [f.to_dict() for f in result.findings]
            emit_event(EventType.APPROVAL_REQUESTED, {"tool": name, "findings": findings})
            from langgraph.types import interrupt

            from app.core.run_context import agent_id_var, thread_id_var
            from app.security.approval import approval_service

            approvals = self._approvals or approval_service
            approval = approvals.get_or_create(
                tool=name,
                args=args,
                findings=findings,
                agent_id=agent_id_var.get(),
                thread_id=thread_id_var.get(),
                tool_call_id=tool_call_id,
            )
            decision = interrupt(
                {
                    "type": "tool_approval",
                    "approval_id": approval.id,
                    "tool": name,
                    "args": args,
                    "findings": findings,
                }
            )

            if str(decision) != "approve":
                emit_event(EventType.GUARD_BLOCK, {"tool": name, "reason": "user_rejected"})
                return ToolMessage(content=t("security.user_rejected"), tool_call_id=tool_call_id, status="error")
            emit_event(EventType.GUARD_APPROVED, {"tool": name})

        return handler(request)
