"""PLAN-130: multi-Agent plan confirmation API and SQLite isolation."""

from __future__ import annotations

import time
from typing import Annotated, Any, TypedDict

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from app.core.checkpoint import CheckpointProvider
from app.core.execution_ref import ExecutionRef


class PlanState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    plan_phase: str
    todos: list[Any]
    owner: str


def _plan_graph(checkpointer, owner: str):
    async def prepare(_state: PlanState) -> PlanState:
        return {"todos": [f"{owner}-step"], "owner": owner}

    async def confirm(state: PlanState) -> PlanState:
        decision = interrupt({"type": "plan_confirm", "todos": state["todos"]})
        return {"messages": [AIMessage(content=f"{owner}:{decision}")]}

    builder = StateGraph(PlanState)
    builder.add_node("prepare", prepare)
    builder.add_node("confirm", confirm)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "confirm")
    builder.add_edge("confirm", END)
    return builder.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_multi_agent_plan_api_isolated_and_recoverable(tmp_path, monkeypatch):
    from app.agents.multi_agent_manager import multi_agent_manager
    from app.api.routes.agent import router
    from app.core import checkpoint as checkpoint_module
    from app.core.agent import agent_manager
    from app.memory.plan_history_store import plan_history_store
    from app.memory.session_store import session_store
    from app.services.execution_resume import graph_resume_adapter

    old_root = multi_agent_manager._root
    old_workspaces = multi_agent_manager._ws
    old_agent = agent_manager._agent
    old_pending = graph_resume_adapter._pending
    first_provider = CheckpointProvider("sqlite", tmp_path / "checkpoints")
    await first_provider.initialize()

    multi_agent_manager._root = tmp_path / "agents"
    multi_agent_manager._ws = {}
    graph_resume_adapter._pending = {}
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", first_provider)
    monkeypatch.setattr(plan_history_store, "path", tmp_path / "plans.json")
    monkeypatch.setattr(session_store, "root", tmp_path / "sessions")
    monkeypatch.setattr(
        multi_agent_manager,
        "_build_agent",
        lambda workspace: _plan_graph(workspace.checkpointer, workspace.agent_id),
    )
    agent_manager._agent = _plan_graph(await first_provider.get("default"), "default")

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)

    async def chat(client, agent_id: str, thread_id: str) -> dict[str, Any]:
        response = await client.post(
            "/api/v1/agent/chat",
            json={"message": "/plan test", "agent_id": agent_id, "thread_id": thread_id},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["execution_ref"]["agent_id"] == agent_id
        assert data["execution_ref"]["thread_id"] == thread_id
        return data

    async def confirm(client, ref: dict[str, Any], decision: str) -> httpx.Response:
        body: dict[str, Any] = {"execution_ref": ref, "decision": decision}
        if decision == "edit":
            body["edited_todos"] = ["edited-step"]
        return await client.post("/api/v1/agent/plan/confirm", json=body)

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # approve/edit/reject each restore the issuing Workspace, even with the
            # same thread id concurrently present in another Workspace.
            for decision in ("approve", "edit", "reject"):
                thread_id = f"shared-{decision}"
                agent_a = f"{decision}-a"
                agent_b = f"{decision}-b"
                multi_agent_manager.create(agent_a)
                multi_agent_manager.create(agent_b)
                pending_a = await chat(client, agent_a, thread_id)
                pending_b = await chat(client, agent_b, thread_id)

                result_a = await confirm(client, pending_a["execution_ref"], decision)
                result_b = await confirm(client, pending_b["execution_ref"], decision)
                assert result_a.status_code == result_b.status_code == 200
                assert result_a.json()["response"].startswith(f"{agent_a}:")
                assert result_b.json()["response"].startswith(f"{agent_b}:")
                assert result_a.json()["agent_id"] == agent_a
                assert result_b.json()["agent_id"] == agent_b

            # History can be filtered by both dimensions and retains full refs.
            history = await client.get(
                "/api/v1/agent/plan/history",
                params={"agent_id": "approve-a", "thread_id": "shared-approve"},
            )
            rows = history.json()["plans"]
            assert [row["action"] for row in rows] == ["approve", "created"]
            assert {row["agent_id"] for row in rows} == {"approve-a"}
            assert all(row["execution_ref"]["agent_id"] == "approve-a" for row in rows)

            # A forged cross-Agent ref is rejected before either graph is resumed.
            mismatch_a = "mismatch-a"
            mismatch_b = "mismatch-b"
            multi_agent_manager.create(mismatch_a)
            multi_agent_manager.create(mismatch_b)
            pending_a = await chat(client, mismatch_a, "same-name")
            pending_b = await chat(client, mismatch_b, "same-name")
            forged = dict(pending_a["execution_ref"])
            forged["agent_id"] = mismatch_b
            rejected = await confirm(client, forged, "approve")
            assert rejected.status_code == 409
            assert "不匹配" in rejected.text
            assert (await confirm(client, pending_b["execution_ref"], "reject")).status_code == 200
            assert (await confirm(client, pending_a["execution_ref"], "approve")).status_code == 200

            # Registry loss through eviction/reload still resolves the original graph.
            for mode in ("evict", "reload"):
                agent_id = f"lifecycle-{mode}"
                multi_agent_manager.create(agent_id)
                pending = await chat(client, agent_id, f"thread-{mode}")
                graph_resume_adapter._pending.clear()
                workspace = multi_agent_manager.get_workspace(agent_id)
                assert workspace is not None
                if mode == "evict":
                    workspace.last_access = time.time() - 10
                    assert agent_id in multi_agent_manager.evict_idle(0)
                else:
                    await multi_agent_manager.reload_agent(agent_id)
                resumed = await confirm(client, pending["execution_ref"], "approve")
                assert resumed.status_code == 200, resumed.text
                assert resumed.json()["response"].startswith(f"{agent_id}:")

            # A fresh provider and rebuilt graph recover the persisted interrupt.
            restart_agent = "lifecycle-restart"
            multi_agent_manager.create(restart_agent)
            restart_pending = await chat(client, restart_agent, "thread-restart")
            graph_resume_adapter._pending.clear()
            await first_provider.close()
            second_provider = CheckpointProvider("sqlite", tmp_path / "checkpoints")
            await second_provider.initialize()
            monkeypatch.setattr(checkpoint_module, "checkpoint_provider", second_provider)
            agent_manager._agent = _plan_graph(
                await second_provider.get("default"),
                "default",
            )
            restart_workspace = multi_agent_manager.get_workspace(restart_agent)
            assert restart_workspace is not None
            restart_workspace.agent = None
            restarted = await confirm(client, restart_pending["execution_ref"], "edit")
            assert restarted.status_code == 200, restarted.text
            assert restarted.json()["response"].startswith(f"{restart_agent}:")

            # Deleted and unknown Agents fail explicitly and never fall back.
            deleted_agent = "deleted-agent"
            multi_agent_manager.create(deleted_agent)
            deleted_pending = await chat(client, deleted_agent, "thread-deleted")
            assert await multi_agent_manager.delete(deleted_agent)
            deleted = await confirm(client, deleted_pending["execution_ref"], "approve")
            assert deleted.status_code == 409
            assert "不可恢复" in deleted.text or "已删除" in deleted.text

            unknown_ref = ExecutionRef(
                agent_id="unknown-agent",
                thread_id="thread-unknown",
                checkpoint_ns="",
                interrupt_id="unknown-interrupt",
                interrupt_type="plan_confirm",
            )
            plan_history_store.record(execution_ref=unknown_ref, action="created")
            unknown = await confirm(client, unknown_ref.model_dump(), "approve")
            assert unknown.status_code == 404
            assert "unknown-agent" in unknown.text

            missing_chat = await client.post(
                "/api/v1/agent/chat",
                json={"message": "hello", "agent_id": "missing-agent"},
            )
            assert missing_chat.status_code == 404

            # Legacy thread-only requests are accepted only for one unique
            # pending default-Agent interrupt.
            default_pending = await chat(client, "default", "legacy-default")
            legacy = await client.post(
                "/api/v1/agent/plan/confirm",
                json={"thread_id": "legacy-default", "decision": "approve"},
            )
            assert legacy.status_code == 200
            assert legacy.json()["execution_ref"] == default_pending["execution_ref"]

            nondefault_pending = await chat(client, restart_agent, "legacy-workspace")
            graph_resume_adapter._pending.pop(
                ExecutionRef.model_validate(nondefault_pending["execution_ref"])
            )
            workspace_legacy = await client.post(
                "/api/v1/agent/plan/confirm",
                json={"thread_id": "legacy-workspace", "decision": "reject"},
            )
            assert workspace_legacy.status_code == 404

            await second_provider.close()
    finally:
        if first_provider.status()["status"] != "closed":
            await first_provider.close()
        multi_agent_manager._root = old_root
        multi_agent_manager._ws = old_workspaces
        agent_manager._agent = old_agent
        graph_resume_adapter._pending = old_pending


def test_plan_history_legacy_json_filters_as_default(tmp_path):
    import json

    from app.memory.plan_history_store import PlanHistoryStore

    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            [{"id": "old", "thread_id": "legacy", "action": "created", "created_at": "2020"}]
        ),
        encoding="utf-8",
    )
    store = PlanHistoryStore(path)

    assert store.list(agent_id="default", thread_id="legacy")[0]["id"] == "old"
    assert store.list(agent_id="other", thread_id="legacy") == []
