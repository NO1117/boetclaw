"""PLAN-200: shared synchronous/SSE request orchestration."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage, AIMessageChunk


def _sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            events.append((event, json.loads("\n".join(data))))
    return events


class FakeAgent:
    def __init__(self, *, interrupt_type: str = "", fail: bool = False) -> None:
        self.interrupt_type = interrupt_type
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        from app.i18n import normalize_lang
        from app.memory.context_policy import normalize_source

        self.calls.append({"state": state, "config": config, "lang": normalize_lang()})
        return {
            "messages": [AIMessage(content=f"sync:{normalize_source('channel')}")],
            "todos": [],
        }

    async def astream(self, state: dict[str, Any], config: dict[str, Any], **_: Any):
        from app.i18n import normalize_lang

        self.calls.append({"state": state, "config": config, "lang": normalize_lang()})
        if self.fail:
            raise RuntimeError("provider unavailable")
        yield ("", "messages", (AIMessageChunk(content="hello"), {}))
        if self.interrupt_type:
            payload: dict[str, Any] = {"type": self.interrupt_type}
            if self.interrupt_type == "tool_approval":
                payload["approval_id"] = "approval-1"
            yield ("", "updates", {"planner": {"todos": ["step"]}})
            yield (
                "",
                "updates",
                {"__interrupt__": [{"id": "interrupt-1", "value": payload}]},
            )


@pytest.fixture
def plan200_app(tmp_path, monkeypatch):
    from app.api.routes.agent import router
    from app.memory.plan_history_store import plan_history_store
    from app.memory.session_store import session_store
    from app.services import chat_orchestration
    from app.services.execution_resume import graph_resume_adapter

    agents = {
        "default": FakeAgent(),
        "workspace": FakeAgent(),
        "planner": FakeAgent(interrupt_type="plan_confirm"),
        "broken": FakeAgent(fail=True),
    }
    resolved: list[str] = []

    async def resolve(agent_id: str):
        resolved.append(agent_id)
        if agent_id not in agents:
            error = ValueError(f"missing: {agent_id}")
            error.status_code = 404  # type: ignore[attr-defined]
            raise error
        return agents[agent_id]

    monkeypatch.setattr(chat_orchestration, "resolve_agent_graph", resolve)
    monkeypatch.setattr(session_store, "root", tmp_path / "sessions")
    monkeypatch.setattr(plan_history_store, "path", tmp_path / "plans.json")
    monkeypatch.setattr(graph_resume_adapter, "register", lambda *_: None)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app, agents, resolved


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id", ["default", "workspace"])
async def test_stream_routes_default_and_nondefault_with_shared_metadata(plan200_app, agent_id):
    from app.memory.session_store import session_store

    app, agents, resolved = plan200_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={
                "message": "hello",
                "thread_id": f"thread-{agent_id}",
                "agent_id": agent_id,
                "source": "cron",
            },
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert resolved == [agent_id]
    assert agents[agent_id].calls[0]["lang"] == "en"
    assert [name for name, _ in events].count("done") == 1
    assert events[-1][0] == "done"
    assert all(payload["version"] == "1" for _, payload in events)
    assert all(payload["agent_id"] == agent_id for _, payload in events)
    assert all(payload["thread_id"] == f"thread-{agent_id}" for _, payload in events)
    assert len({payload["trace_id"] for _, payload in events}) == 1
    assert len({payload["run_id"] for _, payload in events}) == 1
    session = session_store.get_session(f"thread-{agent_id}")
    assert session is not None
    assert session["source"] == "cron"


@pytest.mark.asyncio
async def test_sync_uses_same_resolver_language_source_and_session_policy(plan200_app):
    from app.memory.session_store import session_store

    app, agents, resolved = plan200_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "hello",
                "thread_id": "sync-thread",
                "agent_id": "workspace",
                "source": "heartbeat",
                "lang": "en",
            },
        )

    assert response.status_code == 200
    assert resolved == ["workspace"]
    assert agents["workspace"].calls[0]["lang"] == "en"
    assert response.json()["agent_id"] == "workspace"
    session = session_store.get_session("sync-thread")
    assert session is not None
    assert session["source"] == "heartbeat"
    assert len(session["messages"]) == 2


@pytest.mark.asyncio
async def test_plan_stream_interrupt_is_persisted_once_and_never_reaches_agent_as_slash(plan200_app):
    from app.memory.session_store import session_store

    app, agents, _ = plan200_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={
                "message": "/plan drill",
                "thread_id": "plan-thread",
                "agent_id": "planner",
                "source": "channel",
                "lang": "zh",
            },
        )

    events = _sse_events(response.text)
    interrupt = next(payload for name, payload in events if name == "interrupt")
    assert interrupt["data"]["execution_ref"] == {
        "agent_id": "planner",
        "thread_id": "plan-thread",
        "checkpoint_ns": "",
        "interrupt_id": "interrupt-1",
        "interrupt_type": "plan_confirm",
    }
    assert agents["planner"].calls[0]["state"]["plan_phase"] == "planning"
    assert agents["planner"].calls[0]["state"]["messages"][0]["content"] == "drill"
    session = session_store.get_session("plan-thread")
    assert session is not None
    assert len(session["messages"]) == 2
    assert session["source"] == "channel"
    assert [name for name, _ in events].count("done") == 1


@pytest.mark.asyncio
async def test_stream_slash_command_bypasses_resolver_llm_and_session(plan200_app):
    from app.memory.session_store import session_store

    app, agents, resolved = plan200_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={"message": "/help", "thread_id": "command-thread", "lang": "en"},
        )

    events = _sse_events(response.text)
    assert [name for name, _ in events] == ["command", "done"]
    assert "Available commands:" in events[0][1]["data"]["response"]
    assert not resolved
    assert not agents["default"].calls
    assert session_store.get_session("command-thread") is None


@pytest.mark.asyncio
async def test_stream_error_is_visible_without_done_or_session(plan200_app):
    from app.memory.session_store import session_store

    app, _, _ = plan200_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={"message": "fail", "thread_id": "error-thread", "agent_id": "broken"},
        )

    events = _sse_events(response.text)
    assert [name for name, _ in events] == ["error"]
    assert "provider unavailable" in events[0][1]["data"]["error"]
    assert session_store.get_session("error-thread") is None
