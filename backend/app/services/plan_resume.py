"""Plan-confirmation resume service."""

from __future__ import annotations

from typing import Any

from app.core.execution_ref import ExecutionRef
from app.memory.plan_history_store import plan_history_store
from app.services.execution_resume import ResumeValidationError, graph_resume_adapter


class PlanResumeService:
    async def resume(
        self,
        *,
        decision: str,
        execution_ref: ExecutionRef | None = None,
        thread_id: str = "",
        edited_todos: list[Any] | None = None,
    ) -> dict[str, Any]:
        if execution_ref is not None:
            if execution_ref.interrupt_type != "plan_confirm":
                raise ResumeValidationError("execution_ref 不是计划确认中断", 422)
            if thread_id and thread_id != execution_ref.thread_id:
                raise ResumeValidationError("thread_id 与 execution_ref 不匹配", 409)
            if not plan_history_store.has_pending(execution_ref):
                raise ResumeValidationError("execution_ref 与待确认计划不匹配或已处理", 409)
            ref = execution_ref
        else:
            ref = graph_resume_adapter.find_default(thread_id, "plan_confirm")
        resume_value: Any = (
            {"decision": decision, "edited_todos": edited_todos or []}
            if decision == "edit"
            else decision
        )
        try:
            result = await graph_resume_adapter.resume(
                ref,
                expected_type="plan_confirm",
                resume_value=resume_value,
            )
        except Exception as exc:
            plan_history_store.record(
                execution_ref=ref,
                action=f"{decision}_failed",
                edited_todos=edited_todos,
                response=str(exc),
            )
            raise

        messages = result.get("messages", [])
        last_msg = messages[-1] if messages else None
        content = getattr(last_msg, "content", str(last_msg)) if last_msg else ""
        plan_history_store.record(
            execution_ref=ref,
            action=decision,
            edited_todos=edited_todos,
            response=str(content),
        )
        return {
            "execution_ref": ref.model_dump(),
            "agent_id": ref.agent_id,
            "thread_id": ref.thread_id,
            "interrupt_id": ref.interrupt_id,
            "resumed": True,
            "decision": decision,
            "edited_todos": edited_todos or [],
            "response": content,
            "message_count": len(messages),
        }


plan_resume_service = PlanResumeService()
