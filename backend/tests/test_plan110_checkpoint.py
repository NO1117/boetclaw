"""PLAN-110: real SQLite checkpoint persistence and restart recovery."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from app.core.checkpoint import CheckpointProvider
from app.core.execution_ref import ExecutionRef
from app.security.approval import ApprovalService
from app.services.approval_resume import ApprovalResumeService
from app.services.execution_resume import GraphResumeAdapter, ResumeValidationError


class ValueState(TypedDict, total=False):
    value: str
    resumed: str


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    todos: list[Any]
    plan_phase: str
    resumed: str


def _value_graph(checkpointer, *, interrupting: bool = False):
    async def run(state: ValueState) -> ValueState:
        if interrupting:
            return {"resumed": interrupt({"type": "plan_confirm"})}
        return {"value": state["value"]}

    builder = StateGraph(ValueState)
    builder.add_node("run", run)
    builder.add_edge(START, "run")
    builder.add_edge("run", END)
    return builder.compile(checkpointer=checkpointer)


def _default_agent_graph(checkpointer):
    async def run(state: AgentState) -> AgentState:
        decision = interrupt({"type": "plan_confirm", "todos": state.get("todos", [])})
        return {"resumed": str(decision)}

    builder = StateGraph(AgentState)
    builder.add_node("run", run)
    builder.add_edge(START, "run")
    builder.add_edge("run", END)
    return builder.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_sqlite_checkpoint_can_be_read_after_provider_rebuild(tmp_path):
    config = {"configurable": {"thread_id": "persisted", "checkpoint_ns": ""}}
    first = CheckpointProvider("sqlite", tmp_path)
    await first.initialize()
    graph = _value_graph(await first.get("default"))
    await graph.ainvoke({"value": "stored"}, config=config)
    await first.close()

    second = CheckpointProvider("sqlite", tmp_path)
    await second.initialize()
    rebuilt = _value_graph(await second.get("default"))
    snapshot = await rebuilt.aget_state(config)
    assert snapshot.values["value"] == "stored"
    await second.close()


@pytest.mark.asyncio
async def test_default_agent_interrupt_resumes_after_agent_instance_rebuild(tmp_path, monkeypatch):
    from app.core import checkpoint as checkpoint_module
    from app.core.agent import AgentManager
    from app.core.agent_factory import BoetClawAgentFactory

    first_provider = CheckpointProvider("sqlite", tmp_path)
    await first_provider.initialize()
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", first_provider)
    monkeypatch.setattr(
        BoetClawAgentFactory,
        "build",
        staticmethod(lambda **kwargs: _default_agent_graph(kwargs["checkpointer"])),
    )

    first_manager = AgentManager()
    await first_manager.initialize()
    interrupted = await first_manager.invoke("/plan test", "same-thread")
    ref = ExecutionRef.model_validate(interrupted["execution_ref"])
    await first_provider.close()

    second_provider = CheckpointProvider("sqlite", tmp_path)
    await second_provider.initialize()
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", second_provider)
    second_manager = AgentManager()
    await second_manager.initialize()

    adapter = GraphResumeAdapter(lambda execution_ref: _resolved(second_manager.agent))
    result = await adapter.resume(
        ref,
        expected_type="plan_confirm",
        resume_value="approve",
    )
    assert result["resumed"] == "approve"
    await second_provider.close()


async def _resolved(agent):
    return agent


@pytest.mark.asyncio
async def test_same_thread_is_isolated_between_agent_databases(tmp_path):
    provider = CheckpointProvider("sqlite", tmp_path)
    await provider.initialize()
    config = {"configurable": {"thread_id": "shared-thread", "checkpoint_ns": ""}}
    graph_a = _value_graph(await provider.get("agent-a"))
    graph_b = _value_graph(await provider.get("agent-b"))

    await graph_a.ainvoke({"value": "A"}, config=config)
    await graph_b.ainvoke({"value": "B"}, config=config)

    assert (await graph_a.aget_state(config)).values["value"] == "A"
    assert (await graph_b.aget_state(config)).values["value"] == "B"
    assert provider.database_path("agent-a") != provider.database_path("agent-b")
    await provider.close()


@pytest.mark.asyncio
async def test_memory_mode_status_explicitly_disables_restart_resume(tmp_path):
    provider = CheckpointProvider("memory", tmp_path)
    await provider.initialize()
    status = provider.status()
    assert status["backend"] == "memory"
    assert status["persistent"] is False
    assert status["supports_restart_resume"] is False
    assert "不支持跨重启" in status["warning"]
    await provider.close()


@pytest.mark.asyncio
async def test_invalid_backend_initialization_degrades_without_memory_fallback(tmp_path):
    provider = CheckpointProvider("invalid", tmp_path)

    with pytest.raises(ValueError, match="sqlite 或 memory"):
        await provider.initialize()

    status = provider.status()
    assert status["status"] == "error"
    assert status["backend"] == "invalid"
    assert status["persistent"] is False
    assert status["open_agent_savers"] == 0
    assert "配置无效" in status["warning"]
    await provider.close()


@pytest.mark.asyncio
async def test_provider_close_closes_sqlite_connection(tmp_path):
    provider = CheckpointProvider("sqlite", tmp_path)
    await provider.initialize()
    saver = await provider.get("default")
    await provider.close()

    with pytest.raises(ValueError, match="no active connection"):
        await saver.aget_tuple(
            {"configurable": {"thread_id": "closed", "checkpoint_ns": ""}}
        )
    with pytest.raises(RuntimeError, match="已关闭"):
        await provider.get("default")


@pytest.mark.asyncio
async def test_persisted_resume_returns_409_when_interrupt_is_missing(tmp_path):
    provider = CheckpointProvider("sqlite", tmp_path)
    await provider.initialize()
    graph = _value_graph(await provider.get("default"))
    config = {"configurable": {"thread_id": "completed", "checkpoint_ns": ""}}
    await graph.ainvoke({"value": "done"}, config=config)
    ref = ExecutionRef(
        agent_id="default",
        thread_id="completed",
        checkpoint_ns="",
        interrupt_id="missing",
        interrupt_type="plan_confirm",
    )
    adapter = GraphResumeAdapter(lambda execution_ref: _resolved(graph))
    with pytest.raises(ResumeValidationError, match="不可恢复") as exc_info:
        await adapter.resume(ref, expected_type="plan_confirm", resume_value="approve")
    assert exc_info.value.status_code == 409
    await provider.close()


@pytest.mark.asyncio
async def test_persisted_resume_validates_interrupt_type_from_checkpoint(tmp_path):
    provider = CheckpointProvider("sqlite", tmp_path)
    await provider.initialize()
    graph = _value_graph(await provider.get("default"), interrupting=True)
    config = {"configurable": {"thread_id": "typed", "checkpoint_ns": ""}}
    interrupted = await graph.ainvoke({"value": "waiting"}, config=config)
    real_ref = ExecutionRef(
        agent_id="default",
        thread_id="typed",
        checkpoint_ns="",
        interrupt_id=interrupted["__interrupt__"][0].id,
        interrupt_type="plan_confirm",
    )
    forged_ref = real_ref.model_copy(update={"interrupt_type": "tool_approval"})

    adapter = GraphResumeAdapter(lambda execution_ref: _resolved(graph))
    with pytest.raises(ResumeValidationError, match="不匹配") as exc_info:
        await adapter.resume(
            forged_ref,
            expected_type="tool_approval",
            resume_value="approve",
        )
    assert exc_info.value.status_code == 409
    assert (await graph.aget_state(config)).tasks[0].interrupts
    await provider.close()


@pytest.mark.asyncio
async def test_missing_persisted_interrupt_marks_approval_unrecoverable(tmp_path):
    provider = CheckpointProvider("sqlite", tmp_path / "checkpoints")
    await provider.initialize()
    graph = _value_graph(await provider.get("default"))
    config = {"configurable": {"thread_id": "completed-approval", "checkpoint_ns": ""}}
    await graph.ainvoke({"value": "done"}, config=config)
    ref = ExecutionRef(
        agent_id="default",
        thread_id="completed-approval",
        checkpoint_ns="",
        interrupt_id="missing",
        interrupt_type="tool_approval",
    )
    approvals = ApprovalService(tmp_path / "approvals.json")
    approval = approvals.create("write_file", {}, [], execution_ref=ref)
    service = ApprovalResumeService(
        approvals,
        GraphResumeAdapter(lambda execution_ref: _resolved(graph)),
    )

    with pytest.raises(ResumeValidationError, match="不可恢复") as exc_info:
        await service.resume(
            approval_id=approval.id,
            execution_ref=ref,
            decision="approve",
        )
    assert exc_info.value.status_code == 409
    assert approvals.get(approval.id).status == "resume_failed"
    await provider.close()


def test_memory_restart_expires_old_pending_approvals(tmp_path):
    path = tmp_path / "approvals.json"
    approvals = ApprovalService(path)
    ref = ExecutionRef(
        agent_id="default",
        thread_id="memory-restart",
        checkpoint_ns="",
        interrupt_id="lost",
        interrupt_type="tool_approval",
    )
    approval = approvals.create("write_file", {}, [], execution_ref=ref)

    restored = ApprovalService(path)
    changed = restored.expire_pending_for_restart("memory")

    assert changed == 1
    expired = restored.get(approval.id)
    assert expired.status == "expired"
    assert "memory" in expired.error


def test_sqlite_restart_keeps_pending_for_checkpoint_validation(tmp_path):
    path = tmp_path / "approvals.json"
    approvals = ApprovalService(path)
    ref = ExecutionRef(
        agent_id="default",
        thread_id="sqlite-restart",
        checkpoint_ns="",
        interrupt_id="persisted",
        interrupt_type="tool_approval",
    )
    approval = approvals.create("write_file", {}, [], execution_ref=ref)

    restored = ApprovalService(path)
    changed = restored.expire_pending_for_restart("sqlite")

    assert changed == 0
    assert restored.get(approval.id).status == "pending"
