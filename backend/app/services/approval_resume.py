"""Tool-approval resume service."""

from __future__ import annotations

from typing import Any

from app.core.execution_ref import ExecutionRef
from app.security.approval import ApprovalService, ApprovalStateError, approval_service
from app.services.execution_resume import GraphResumeAdapter, ResumeValidationError, graph_resume_adapter


class ApprovalResumeService:
    def __init__(
        self,
        approvals: ApprovalService = approval_service,
        adapter: GraphResumeAdapter = graph_resume_adapter,
    ) -> None:
        self.approvals = approvals
        self.adapter = adapter

    async def resume(
        self,
        *,
        approval_id: str,
        decision: str,
        execution_ref: ExecutionRef | None = None,
        thread_id: str = "",
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ResumeValidationError("decision 必须是 approve 或 reject", 422)
        approval = self.approvals.get(approval_id)
        if approval is None:
            raise ResumeValidationError("审批记录不存在", 404)
        if approval.status != "pending":
            raise ResumeValidationError(f"审批已不可恢复：{approval.status}", 409)
        if approval.execution_ref is None:
            raise ResumeValidationError("历史审批缺少 execution_ref，只能查看，不能恢复", 409)

        stored_ref = approval.execution_ref
        if execution_ref is None:
            if stored_ref.agent_id != "default" or not thread_id:
                raise ResumeValidationError("必须提供完整 execution_ref", 422)
            if thread_id != stored_ref.thread_id:
                raise ResumeValidationError("thread_id 与审批记录不匹配", 409)
            execution_ref = stored_ref
        elif execution_ref != stored_ref:
            raise ResumeValidationError("execution_ref 与审批记录不匹配", 409)
        if execution_ref.interrupt_type != "tool_approval":
            raise ResumeValidationError("execution_ref 不是工具审批中断", 422)

        try:
            self.approvals.begin_resume(approval_id, decision)
        except ApprovalStateError as exc:
            raise ResumeValidationError(str(exc), 409) from exc

        try:
            result = await self.adapter.resume(
                execution_ref,
                expected_type="tool_approval",
                resume_value=decision,
            )
        except Exception as exc:
            self.approvals.mark_resume_failed(approval_id, str(exc))
            raise

        resolved = self.approvals.resolve(approval_id, decision)
        if resolved is None:
            raise ResumeValidationError("审批状态已变化", 409)
        return {
            "resumed": True,
            "decision": decision,
            "approval": resolved.to_dict(),
            "execution_ref": execution_ref.model_dump(),
            "result": _result_summary(result),
        }


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    messages = result.get("messages", [])
    last_msg = messages[-1] if messages else None
    return {
        "response": getattr(last_msg, "content", str(last_msg)) if last_msg else "",
        "message_count": len(messages),
    }


approval_resume_service = ApprovalResumeService()
