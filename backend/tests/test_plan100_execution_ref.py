"""PLAN-100: execution references and fail-closed resume semantics."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.execution_ref import ExecutionRef, parse_interrupt
from app.memory.plan_history_store import PlanHistoryStore
from app.security.approval import ApprovalService
from app.services.approval_resume import ApprovalResumeService
from app.services.execution_resume import GraphResumeAdapter, ResumeValidationError


def _ref(interrupt_type: str = "plan_confirm", **changes) -> ExecutionRef:
    values = {
        "agent_id": "default",
        "thread_id": "thread-100",
        "checkpoint_ns": "",
        "interrupt_id": "interrupt-100",
        "interrupt_type": interrupt_type,
    }
    values.update(changes)
    return ExecutionRef(**values)


def test_execution_ref_is_frozen_and_validated():
    ref = _ref()
    with pytest.raises(ValidationError):
        ref.thread_id = "other"
    with pytest.raises(ValidationError):
        ExecutionRef(
            agent_id="",
            thread_id="thread",
            checkpoint_ns="",
            interrupt_id="interrupt",
            interrupt_type="plan_confirm",
        )


def test_interrupt_parser_supports_dict_and_langgraph_object():
    payload = {"type": "plan_confirm", "todos": ["one"]}
    dict_envelope = parse_interrupt(
        {"id": "dict-id", "value": payload},
        agent_id="default",
        thread_id="thread",
        checkpoint_ns="",
    )
    object_envelope = parse_interrupt(
        SimpleNamespace(id="object-id", value=payload),
        agent_id="agent-a",
        thread_id="thread",
        checkpoint_ns="child",
    )

    assert dict_envelope is not None
    assert dict_envelope.execution_ref.interrupt_id == "dict-id"
    assert dict_envelope.payload == payload
    assert object_envelope is not None
    assert object_envelope.execution_ref.agent_id == "agent-a"
    assert object_envelope.execution_ref.checkpoint_ns == "child"
    assert parse_interrupt(
        {"value": payload},
        agent_id="default",
        thread_id="thread",
        checkpoint_ns="",
    ) is None


@pytest.mark.asyncio
async def test_wrong_execution_ref_does_not_resume_graph():
    class FakeAgent:
        calls = 0

        async def ainvoke(self, state, config):
            self.calls += 1
            return {}

    adapter = GraphResumeAdapter()
    agent = FakeAgent()
    adapter.register(_ref(), agent)

    with pytest.raises(ResumeValidationError, match="不存在或已恢复"):
        await adapter.resume(
            _ref(interrupt_id="wrong"),
            expected_type="plan_confirm",
            resume_value="approve",
        )
    assert agent.calls == 0


@pytest.mark.asyncio
async def test_approval_is_resolved_only_after_resume_success(tmp_path):
    approvals = ApprovalService(tmp_path / "approvals.json")
    ref = _ref("tool_approval")
    approval = approvals.create("write_file", {"file_path": "a.md"}, [], execution_ref=ref)

    class InspectingAdapter:
        async def resume(self, execution_ref, *, expected_type, resume_value):
            assert approvals.get(approval.id).status == "resuming"
            assert expected_type == "tool_approval"
            return {}

    service = ApprovalResumeService(approvals, InspectingAdapter())
    await service.resume(
        approval_id=approval.id,
        execution_ref=ref,
        decision="approve",
    )
    assert approvals.get(approval.id).status == "approved"


@pytest.mark.asyncio
async def test_approval_resume_failure_records_failed_not_approved(tmp_path):
    approvals = ApprovalService(tmp_path / "approvals.json")
    ref = _ref("tool_approval")
    approval = approvals.create("write_file", {}, [], execution_ref=ref)

    class FailingAdapter:
        async def resume(self, execution_ref, *, expected_type, resume_value):
            raise RuntimeError("checkpoint unavailable")

    service = ApprovalResumeService(approvals, FailingAdapter())
    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        await service.resume(
            approval_id=approval.id,
            execution_ref=ref,
            decision="approve",
        )
    restored = approvals.get(approval.id)
    assert restored.status == "resume_failed"
    assert "checkpoint unavailable" in restored.error


@pytest.mark.asyncio
async def test_approval_adapter_validation_failure_is_audited(tmp_path):
    approvals = ApprovalService(tmp_path / "approvals.json")
    ref = _ref("tool_approval")
    approval = approvals.create("write_file", {}, [], execution_ref=ref)

    class MissingCheckpointAdapter:
        async def resume(self, execution_ref, *, expected_type, resume_value):
            raise ResumeValidationError("execution_ref 不存在或已恢复", 409)

    service = ApprovalResumeService(approvals, MissingCheckpointAdapter())
    with pytest.raises(ResumeValidationError, match="不存在或已恢复"):
        await service.resume(
            approval_id=approval.id,
            execution_ref=ref,
            decision="approve",
        )

    restored = approvals.get(approval.id)
    assert restored.status == "resume_failed"
    assert "不存在或已恢复" in restored.error


@pytest.mark.asyncio
async def test_legacy_approval_json_is_read_only(tmp_path):
    path = tmp_path / "approvals.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy",
                    "tool": "write_file",
                    "args": {},
                    "findings": [],
                    "thread_id": "old-thread",
                    "status": "approved",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    approvals = ApprovalService(path)
    legacy = approvals.get("legacy")
    assert legacy is not None
    assert legacy.execution_ref is None
    assert legacy.to_dict()["execution_ref"] is None

    legacy.status = "pending"
    service = ApprovalResumeService(approvals, GraphResumeAdapter())
    with pytest.raises(ResumeValidationError, match="只能查看"):
        await service.resume(
            approval_id="legacy",
            thread_id="old-thread",
            decision="reject",
        )


def test_plan_history_reads_legacy_json_and_writes_execution_ref(tmp_path):
    path = tmp_path / "plans.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy-plan",
                    "thread_id": "old-thread",
                    "action": "created",
                    "todos": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    store = PlanHistoryStore(path)
    assert store.list("old-thread")[0].get("execution_ref") is None

    row = store.record(execution_ref=_ref(), action="created", todos=["one"])
    assert row["execution_ref"]["interrupt_id"] == "interrupt-100"


def test_tool_guard_interrupt_failure_is_fail_closed(monkeypatch):
    import langgraph.types

    from app.middleware.tool_guard_mw import ToolGuardMiddleware
    from app.security.approval import approval_service

    middleware = ToolGuardMiddleware()
    middleware._engine = SimpleNamespace(
        evaluate=lambda name, args: SimpleNamespace(
            allowed=True,
            requires_approval=True,
            findings=[],
        )
    )
    monkeypatch.setattr(
        approval_service,
        "get_or_create",
        lambda **kwargs: SimpleNamespace(id="approval-100"),
    )
    monkeypatch.setattr(
        langgraph.types,
        "interrupt",
        lambda payload: (_ for _ in ()).throw(RuntimeError("outside graph")),
    )
    executed = False

    def handler(request):
        nonlocal executed
        executed = True

    request = SimpleNamespace(
        tool_call={"name": "write_file", "args": {"file_path": "a.md"}, "id": "tool-1"}
    )
    with pytest.raises(RuntimeError, match="outside graph"):
        middleware.wrap_tool_call(request, handler)
    assert executed is False


@pytest.mark.asyncio
async def test_plan_and_approval_interrupt_types_are_not_interchangeable(tmp_path):
    class FakeAgent:
        calls = 0

        async def ainvoke(self, state, config):
            self.calls += 1
            return {}

    adapter = GraphResumeAdapter()
    agent = FakeAgent()
    plan_ref = _ref("plan_confirm")
    adapter.register(plan_ref, agent)

    with pytest.raises(ResumeValidationError, match="中断类型不匹配"):
        await adapter.resume(
            plan_ref,
            expected_type="tool_approval",
            resume_value="approve",
        )
    assert agent.calls == 0
