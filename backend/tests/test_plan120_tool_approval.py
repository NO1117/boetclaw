"""PLAN-120: real LangGraph tool-approval interrupt and resume coverage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TypedDict

import pytest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.checkpoint import CheckpointProvider
from app.core.execution_ref import ExecutionRef, parse_interrupt_result
from app.core.run_context import reset_run_context, set_run_context
from app.middleware.tool_guard_mw import ToolGuardMiddleware
from app.security.approval import ApprovalService
from app.services.approval_resume import ApprovalResumeService
from app.services.execution_resume import GraphResumeAdapter, ResumeValidationError


class ToolState(TypedDict, total=False):
    result: str


def _tool_graph(checkpointer, approvals: ApprovalService, calls: list[str]):
    middleware = ToolGuardMiddleware(approvals)
    middleware._engine = SimpleNamespace(
        evaluate=lambda name, args: SimpleNamespace(
            allowed=True,
            requires_approval=True,
            findings=[
                SimpleNamespace(
                    to_dict=lambda: {
                        "severity": "high",
                        "category": "write",
                        "message": "测试风险",
                        "guardian": "test",
                    }
                )
            ],
        )
    )

    def run(state: ToolState) -> ToolState:
        request = SimpleNamespace(
            tool_call={
                "name": "write_file",
                "args": {"file_path": "approved.txt"},
                "id": "stable-tool-call",
            }
        )

        def handler(_request):
            calls.append("executed")
            return ToolMessage(content="executed", tool_call_id="stable-tool-call")

        message = middleware.wrap_tool_call(request, handler)
        return {"result": message.content}

    builder = StateGraph(ToolState)
    builder.add_node("guarded_tool", run)
    builder.add_edge(START, "guarded_tool")
    builder.add_edge("guarded_tool", END)
    return builder.compile(checkpointer=checkpointer)


async def _interrupt(
    graph,
    approvals: ApprovalService,
    *,
    agent_id: str,
    thread_id: str,
) -> tuple[ExecutionRef, str]:
    tokens = set_run_context(agent_id=agent_id, thread_id=thread_id)
    try:
        result = await graph.ainvoke(
            {},
            config={"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        )
    finally:
        reset_run_context(tokens)
    envelope = parse_interrupt_result(
        result,
        agent_id=agent_id,
        thread_id=thread_id,
        checkpoint_ns="",
    )
    assert envelope is not None
    approval_id = envelope.payload["approval_id"]
    assert approvals.bind_execution_ref(approval_id, envelope.execution_ref)
    return envelope.execution_ref, approval_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_calls", "expected_status"),
    [("approve", 1, "approved"), ("reject", 0, "rejected")],
)
async def test_real_langgraph_approval_executes_handler_at_most_once(
    tmp_path,
    decision,
    expected_calls,
    expected_status,
):
    approvals = ApprovalService(tmp_path / f"{decision}.json")
    calls: list[str] = []
    graph = _tool_graph(MemorySaver(), approvals, calls)
    ref, approval_id = await _interrupt(
        graph,
        approvals,
        agent_id="default",
        thread_id=f"real-{decision}",
    )
    adapter = GraphResumeAdapter()
    adapter.register(ref, graph)

    result = await ApprovalResumeService(approvals, adapter).resume(
        approval_id=approval_id,
        execution_ref=ref,
        decision=decision,
    )

    assert len(calls) == expected_calls
    assert approvals.get(approval_id).status == expected_status
    assert len(approvals.list_all()) == 1
    assert result["approval"]["decision"] == decision


@pytest.mark.asyncio
async def test_replayed_node_reuses_one_pending_approval(tmp_path):
    approvals = ApprovalService(tmp_path / "replay.json")
    calls: list[str] = []
    graph = _tool_graph(MemorySaver(), approvals, calls)
    ref, approval_id = await _interrupt(
        graph,
        approvals,
        agent_id="default",
        thread_id="replay",
    )
    adapter = GraphResumeAdapter()
    adapter.register(ref, graph)

    await ApprovalResumeService(approvals, adapter).resume(
        approval_id=approval_id,
        execution_ref=ref,
        decision="approve",
    )

    assert calls == ["executed"]
    assert [row.id for row in approvals.list_all()] == [approval_id]


@pytest.mark.asyncio
async def test_concurrent_and_repeated_decisions_cannot_execute_twice(tmp_path):
    approvals = ApprovalService(tmp_path / "concurrent.json")
    calls: list[str] = []
    graph = _tool_graph(MemorySaver(), approvals, calls)
    ref, approval_id = await _interrupt(
        graph,
        approvals,
        agent_id="default",
        thread_id="concurrent",
    )
    adapter = GraphResumeAdapter()
    adapter.register(ref, graph)
    service = ApprovalResumeService(approvals, adapter)

    results = await asyncio.gather(
        service.resume(approval_id=approval_id, execution_ref=ref, decision="approve"),
        service.resume(approval_id=approval_id, execution_ref=ref, decision="reject"),
        return_exceptions=True,
    )

    assert sum(isinstance(result, ResumeValidationError) for result in results) == 1
    assert calls == ["executed"]
    with pytest.raises(ResumeValidationError, match="不可恢复"):
        await service.resume(approval_id=approval_id, execution_ref=ref, decision="approve")
    assert calls == ["executed"]


@pytest.mark.asyncio
async def test_resume_failure_is_terminal_and_not_approved(tmp_path):
    approvals = ApprovalService(tmp_path / "failed.json")
    ref = ExecutionRef(
        agent_id="default",
        thread_id="failed",
        checkpoint_ns="",
        interrupt_id="failed-interrupt",
        interrupt_type="tool_approval",
    )
    approval = approvals.create("write_file", {}, [], execution_ref=ref)

    class FailingAdapter:
        async def resume(self, *args, **kwargs):
            raise RuntimeError("graph failed")

    service = ApprovalResumeService(approvals, FailingAdapter())
    with pytest.raises(RuntimeError, match="graph failed"):
        await service.resume(
            approval_id=approval.id,
            execution_ref=ref,
            decision="approve",
        )

    failed = approvals.get(approval.id)
    assert failed.status == "resume_failed"
    assert failed.decision == "approve"
    assert "不可自动重试" in failed.error
    with pytest.raises(ResumeValidationError, match="不可恢复"):
        await service.resume(
            approval_id=approval.id,
            execution_ref=ref,
            decision="approve",
        )


def test_restart_converts_inflight_resume_to_terminal_ambiguous_failure(tmp_path):
    path = tmp_path / "restart-inflight.json"
    approvals = ApprovalService(path)
    approval = approvals.create("write_file", {}, [])
    approvals.begin_resume(approval.id, "approve")

    restored = ApprovalService(path).get(approval.id)

    assert restored.status == "resume_failed"
    assert restored.decision == "approve"
    assert "不可自动重试" in restored.error


@pytest.mark.asyncio
async def test_sqlite_resume_after_service_and_adapter_rebuild(tmp_path):
    calls: list[str] = []
    approvals_path = tmp_path / "approvals.json"
    first_provider = CheckpointProvider("sqlite", tmp_path / "checkpoints")
    await first_provider.initialize()
    first_approvals = ApprovalService(approvals_path)
    first_graph = _tool_graph(await first_provider.get("default"), first_approvals, calls)
    ref, approval_id = await _interrupt(
        first_graph,
        first_approvals,
        agent_id="default",
        thread_id="sqlite-rebuild",
    )
    await first_provider.close()

    second_provider = CheckpointProvider("sqlite", tmp_path / "checkpoints")
    await second_provider.initialize()
    restored_approvals = ApprovalService(approvals_path)
    rebuilt_graph = _tool_graph(await second_provider.get("default"), restored_approvals, calls)

    async def resolver(execution_ref):
        assert execution_ref.agent_id == "default"
        return rebuilt_graph

    await ApprovalResumeService(
        restored_approvals,
        GraphResumeAdapter(resolver),
    ).resume(
        approval_id=approval_id,
        execution_ref=ref,
        decision="approve",
    )

    assert calls == ["executed"]
    assert restored_approvals.get(approval_id).status == "approved"
    await second_provider.close()


@pytest.mark.asyncio
async def test_non_default_agent_uses_execution_ref_resolver(tmp_path):
    approvals = ApprovalService(tmp_path / "workspace-agent.json")
    calls: list[str] = []
    graph = _tool_graph(MemorySaver(), approvals, calls)
    ref, approval_id = await _interrupt(
        graph,
        approvals,
        agent_id="workspace-a",
        thread_id="shared-thread",
    )
    resolved: list[ExecutionRef] = []

    async def resolver(execution_ref):
        resolved.append(execution_ref)
        return graph

    await ApprovalResumeService(
        approvals,
        GraphResumeAdapter(resolver),
    ).resume(
        approval_id=approval_id,
        execution_ref=ref,
        decision="approve",
    )

    assert resolved == [ref]
    assert resolved[0].agent_id == "workspace-a"
    assert calls == ["executed"]
