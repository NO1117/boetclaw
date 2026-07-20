"""Shared graph-resume adapter with strict pending-reference validation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.execution_ref import ExecutionRef


class ResumeValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphResumeAdapter:
    def __init__(
        self,
        resolver: Callable[[ExecutionRef], Awaitable[Any]] | None = None,
    ) -> None:
        self._pending: dict[ExecutionRef, Any] = {}
        self._resolver = resolver

    def register(self, execution_ref: ExecutionRef, agent: Any) -> None:
        self._pending[execution_ref] = agent

    def is_pending(self, execution_ref: ExecutionRef) -> bool:
        return execution_ref in self._pending

    def find_default(self, thread_id: str, interrupt_type: str) -> ExecutionRef:
        matches = [
            ref
            for ref in self._pending
            if ref.agent_id == "default"
            and ref.thread_id == thread_id
            and ref.interrupt_type == interrupt_type
        ]
        if not matches:
            raise ResumeValidationError("没有匹配的待恢复中断", 404)
        if len(matches) != 1:
            raise ResumeValidationError("恢复请求存在歧义，必须提供完整 execution_ref", 409)
        return matches[0]

    async def resume(
        self,
        execution_ref: ExecutionRef,
        *,
        expected_type: str,
        resume_value: Any,
    ) -> dict[str, Any]:
        if execution_ref.interrupt_type != expected_type:
            raise ResumeValidationError(
                f"中断类型不匹配：期望 {expected_type}，实际 {execution_ref.interrupt_type}",
                422,
            )
        agent = self._pending.get(execution_ref)
        if self._resolver is not None and (agent is None or execution_ref.agent_id != "default"):
            try:
                resolved_agent = await self._resolver(execution_ref)
            except ResumeValidationError:
                raise
            except Exception as exc:
                status_code = getattr(exc, "status_code", 409)
                raise ResumeValidationError(
                    f"原 Agent 无法重建，checkpoint 不可恢复：{exc}",
                    status_code,
                ) from exc
            if agent is None:
                agent = resolved_agent
        elif agent is None:
            raise ResumeValidationError("execution_ref 不存在或已恢复", 409)
        if execution_ref not in self._pending:
            await self._validate_persisted_interrupt(agent, execution_ref)
        from langgraph.types import Command

        config = {
            "configurable": {
                "thread_id": execution_ref.thread_id,
                "checkpoint_ns": execution_ref.checkpoint_ns,
            }
        }
        from app.core.run_context import reset_run_context, set_run_context

        context_tokens = set_run_context(
            agent_id=execution_ref.agent_id,
            thread_id=execution_ref.thread_id,
        )
        try:
            result = await agent.ainvoke(Command(resume=resume_value), config=config)
        finally:
            reset_run_context(context_tokens)
        self._pending.pop(execution_ref, None)
        return result if isinstance(result, dict) else {}

    async def _validate_persisted_interrupt(
        self,
        agent: Any,
        execution_ref: ExecutionRef,
    ) -> None:
        config = {
            "configurable": {
                "thread_id": execution_ref.thread_id,
                "checkpoint_ns": execution_ref.checkpoint_ns,
            }
        }
        try:
            snapshot = await agent.aget_state(config)
        except Exception as exc:
            raise ResumeValidationError(f"checkpoint 无法读取：{exc}", 409) from exc
        matched_id = False
        for task in getattr(snapshot, "tasks", ()) or ():
            for interrupt in getattr(task, "interrupts", ()) or ():
                interrupt_id = getattr(interrupt, "id", None)
                value = getattr(interrupt, "value", None)
                if interrupt_id is None and isinstance(interrupt, dict):
                    interrupt_id = interrupt.get("id")
                    value = interrupt.get("value")
                if interrupt_id == execution_ref.interrupt_id:
                    matched_id = True
                    interrupt_type = value.get("type") if isinstance(value, dict) else None
                    if interrupt_type == execution_ref.interrupt_type:
                        return
        if matched_id:
            raise ResumeValidationError("checkpoint 中断类型与 execution_ref 不匹配", 409)
        raise ResumeValidationError("checkpoint 不存在或中断已不可恢复", 409)


async def resolve_agent_for_resume(execution_ref: ExecutionRef) -> Any:
    """Rebuild the graph named by a persisted execution reference."""
    from app.agents.multi_agent_manager import multi_agent_manager
    from app.agents.resolver import AgentResolutionError, resolve_agent_graph

    try:
        return await resolve_agent_graph(execution_ref.agent_id)
    except AgentResolutionError as exc:
        agent_id = execution_ref.agent_id
        if multi_agent_manager.is_tombstoned(agent_id) or multi_agent_manager.was_purged(agent_id):
            raise ResumeValidationError(
                f"Agent 已删除或已清除，不可恢复：{agent_id}",
                409,
            ) from exc
        raise ResumeValidationError(str(exc), getattr(exc, "status_code", 404)) from exc


graph_resume_adapter = GraphResumeAdapter(resolve_agent_for_resume)
