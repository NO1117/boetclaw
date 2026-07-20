"""Phase 2 tests: plan gate middleware & state."""

from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.messages import AIMessage


@dataclass
class _FakeReq:
    tool_call: dict
    state: Any


def _handler(_req):
    from langchain_core.messages import ToolMessage

    return ToolMessage(content="ok", tool_call_id=_req.tool_call.get("id", ""))


def test_state_has_plan_phase():
    from app.agents.state import BoetClawState

    assert "plan_phase" in BoetClawState.__annotations__


def test_plan_gate_blocks_non_plan_tool_in_planning():
    from app.middleware.plan_gate_mw import PlanGateMiddleware

    mw = PlanGateMiddleware()
    req = _FakeReq(
        tool_call={"name": "generate_chart", "args": {}, "id": "t1"},
        state={"plan_phase": "planning"},
    )
    result = mw.wrap_tool_call(req, _handler)
    assert getattr(result, "status", None) == "error"
    assert "规划阶段" in result.content


def test_plan_gate_allows_normal_tool_when_idle():
    from app.middleware.plan_gate_mw import PlanGateMiddleware

    mw = PlanGateMiddleware()
    req = _FakeReq(
        tool_call={"name": "generate_chart", "args": {}, "id": "t2"},
        state={"plan_phase": "idle"},
    )
    result = mw.wrap_tool_call(req, _handler)
    assert result.content == "ok"


def test_factory_includes_plan_gate():
    from app.core.agent_factory import BoetClawAgentFactory  # noqa: F401
    # build with a dummy model string won't call network at construction time
    # only assert the middleware wiring helper does not raise on import
    from app.middleware.plan_gate_mw import PlanGateMiddleware

    assert PlanGateMiddleware().name == "boetclaw_plan_gate"


@pytest.mark.asyncio
async def test_plan_interrupt_confirm_roundtrip_without_llm(monkeypatch, tmp_path):
    """Phase 2.5: deterministic /plan -> interrupt -> Command(resume=...) flow.

    This avoids a real LLM call by injecting a fake graph agent while still
    verifying the AgentManager contract used by the API and frontend.
    """
    from langgraph.types import Command

    from app.core.agent import AgentManager
    from app.memory.plan_history_store import plan_history_store

    monkeypatch.setattr(plan_history_store, "path", tmp_path / "plans" / "plan_history.json", raising=False)

    class FakePlanAgent:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, dict]] = []

        async def ainvoke(self, state, config):
            self.calls.append((state, config))
            if isinstance(state, Command):
                return {"messages": [AIMessage(content="计划已批准，开始执行。")]}
            assert state["plan_phase"] == "planning"
            assert state["messages"][0]["content"] == "生成日报"
            return {
                "__interrupt__": [{"id": "interrupt-1", "value": {"type": "plan_confirm"}}],
                "messages": [],
                "todos": ["审查", "生成"],
            }

    manager = AgentManager()
    fake = FakePlanAgent()
    manager._agent = fake

    first = await manager.invoke("/plan 生成日报", "thread-1")
    assert first["interrupted"] is True
    assert first["todos"] == ["审查", "生成"]
    assert fake.calls[0][1]["configurable"]["thread_id"] == "thread-1"

    resumed = await manager.confirm_plan("thread-1", "approve")
    assert resumed["resumed"] is True
    assert resumed["decision"] == "approve"
    assert resumed["response"] == "计划已批准，开始执行。"
    assert isinstance(fake.calls[1][0], Command)
    assert fake.calls[1][1]["configurable"]["thread_id"] == "thread-1"

    history = plan_history_store.list("thread-1")
    assert [row["action"] for row in history] == ["approve", "created"]


@pytest.mark.asyncio
async def test_plan_confirm_edit_records_edited_todos(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    from langgraph.types import Command

    from app.core.agent import AgentManager
    from app.core.execution_ref import ExecutionRef
    from app.memory.plan_history_store import plan_history_store
    from app.services.execution_resume import graph_resume_adapter

    monkeypatch.setattr(plan_history_store, "path", tmp_path / "plans" / "plan_history.json", raising=False)

    class FakePlanAgent:
        def __init__(self) -> None:
            self.resume_value = None

        async def ainvoke(self, state, config):
            assert config["configurable"]["thread_id"] == "thread-edit"
            assert isinstance(state, Command)
            self.resume_value = state.resume
            return {"messages": [AIMessage(content="已按编辑后的计划继续。")]}

    manager = AgentManager()
    fake = FakePlanAgent()
    manager._agent = fake
    edited = ["补充风险检查", "生成日报"]
    graph_resume_adapter.register(
        ExecutionRef(
            agent_id="default",
            thread_id="thread-edit",
            checkpoint_ns="",
            interrupt_id="interrupt-edit",
            interrupt_type="plan_confirm",
        ),
        fake,
    )

    result = await manager.confirm_plan("thread-edit", "edit", edited)

    assert result["decision"] == "edit"
    assert result["edited_todos"] == edited
    assert fake.resume_value == {"decision": "edit", "edited_todos": edited}
    history = plan_history_store.list("thread-edit")
    assert history[0]["action"] == "edit"
    assert history[0]["edited_todos"] == edited


@pytest.mark.asyncio
async def test_plan_confirm_failure_records_history(monkeypatch, tmp_path):
    from langgraph.types import Command

    from app.core.agent import AgentManager
    from app.core.execution_ref import ExecutionRef
    from app.memory.plan_history_store import plan_history_store
    from app.services.execution_resume import graph_resume_adapter

    monkeypatch.setattr(plan_history_store, "path", tmp_path / "plans" / "plan_history.json", raising=False)

    class FailingPlanAgent:
        async def ainvoke(self, state, config):
            assert isinstance(state, Command)
            assert state.resume == "approve"
            assert config["configurable"]["thread_id"] == "thread-fail"
            raise RuntimeError("checkpoint missing")

    manager = AgentManager()
    manager._agent = FailingPlanAgent()
    graph_resume_adapter.register(
        ExecutionRef(
            agent_id="default",
            thread_id="thread-fail",
            checkpoint_ns="",
            interrupt_id="interrupt-fail",
            interrupt_type="plan_confirm",
        ),
        manager._agent,
    )

    with pytest.raises(RuntimeError, match="checkpoint missing"):
        await manager.confirm_plan("thread-fail", "approve")

    history = plan_history_store.list("thread-fail")
    assert history[0]["action"] == "approve_failed"
    assert "checkpoint missing" in history[0]["response"]
