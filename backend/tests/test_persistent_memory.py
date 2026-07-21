"""Persistent user memory tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture
def memory_env(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.memory.service import memory_service
    from app.memory.sqlite_repo import MemorySqliteRepository

    db_dir = tmp_path / "memory"
    repo = MemorySqliteRepository(db_dir / "memories.sqlite3")
    monkeypatch.setattr("app.memory.sqlite_repo.memory_repository", repo)
    monkeypatch.setattr("app.memory.service.memory_repository", repo)
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setattr(settings, "memory_sqlite_path", db_dir)
    monkeypatch.setattr(settings, "memory_backend", "sqlite")
    monkeypatch.setattr(settings, "memory_auto_mode", "review")
    memory_service._enabled = False
    memory_service._fallback = False
    memory_service._backend = "sqlite"
    memory_service.initialize()
    yield repo, memory_service
    memory_service.close()


@pytest.fixture
def memory_api(memory_env, monkeypatch):
    from app.api.routes import agent as agent_routes
    from app.api.routes import memories as memories_routes
    from app.core.agent_factory import BoetClawAgentFactory
    from app.memory.session_store import session_store
    from app.providers.manager import provider_manager
    from app.services import chat_orchestration

    class FakeAgent:
        calls: list[dict] = []

        async def ainvoke(self, state, config):
            from langchain_core.messages import AIMessage

            FakeAgent.calls.append({"state": state, "config": config})
            return {"messages": [AIMessage(content="ok")], "todos": []}

        async def astream(self, state, config, **_):
            from langchain_core.messages import AIMessageChunk

            FakeAgent.calls.append({"state": state, "config": config})
            yield ("", "messages", (AIMessageChunk(content="ok"), {}))

    FakeAgent.calls = []
    cached = FakeAgent()

    async def resolve(_agent_id: str):
        return cached

    monkeypatch.setattr(chat_orchestration, "resolve_agent_graph", resolve)
    monkeypatch.setattr(provider_manager, "get_chat_model", lambda *a, **k: "model:fake")
    monkeypatch.setattr(BoetClawAgentFactory, "build", staticmethod(lambda **k: FakeAgent()))
    monkeypatch.setattr(session_store, "root", memory_env[0].db_path.parent / "sessions")

    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/v1")
    app.include_router(memories_routes.router, prefix="/api/v1")
    return app, cached, memory_env[1]


def test_sensitive_content_rejected(memory_env):
    _, service = memory_env
    with pytest.raises(ValueError, match="凭据"):
        service.create_manual(agent_id="default", content="password=secret123")


def test_duplicate_detection(memory_env):
    _, service = memory_env
    service.create_manual(agent_id="default", content="我喜欢使用中文回复")
    with pytest.raises(ValueError, match="相同"):
        service.create_manual(agent_id="default", content="我喜欢使用中文回复")


def test_agent_isolation(memory_env):
    repo, service = memory_env
    service.create_manual(agent_id="agent-a", content="Agent A 私有偏好")
    assert service.get("agent-b", service.list_memories("agent-a")["items"][0]["id"]) is None
    rows_b, _ = repo.list_memories("agent-b")
    assert rows_b == []


def test_review_candidate_pending_not_retrieved(memory_env):
    repo, service = memory_env
    from app.core.config import settings

    settings.memory_auto_mode = "review"
    _, summary, _, candidates = service.prepare_chat_memory(
        agent_id="default",
        thread_id="t1",
        message="我的偏好是使用 Markdown 输出",
        source="user",
        trace_id="trace-1",
        user_content="hello",
    )
    assert candidates
    assert candidates[0].id
    record = service.get("default", candidates[0].id)
    assert record is not None
    assert record.status == "pending"
    hits = repo.retrieve_for_context("default", thread_id="t1", query="Markdown", limit=5)
    assert hits == []


def test_explicit_remember(memory_env):
    _, service = memory_env
    content, summary, actions, _ = service.prepare_chat_memory(
        agent_id="default",
        thread_id="t1",
        message="请记住：默认使用中文",
        source="user",
        trace_id="trace-2",
        user_content="msg",
    )
    assert "msg" in str(content)
    assert "用户记忆" in str(content)
    assert actions and actions[0].success
    assert summary.saved_count >= 1


def test_automation_source_skips_candidate(memory_env):
    _, service = memory_env
    _, _, actions, candidates = service.prepare_chat_memory(
        agent_id="default",
        thread_id="t1",
        message="我的偏好是使用中文",
        source="cron",
        trace_id="trace-3",
        user_content="msg",
    )
    assert candidates == []
    assert actions == []


@pytest.mark.asyncio
async def test_memory_api_crud(memory_api):
    app, _, _ = memory_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/memories",
            json={"agent_id": "default", "content": "长期目标：提升钻井日报质量", "scope": "agent"},
        )
        assert created.status_code == 200
        memory_id = created.json()["id"]
        listed = await client.get("/api/v1/memories", params={"agent_id": "default"})
        assert listed.json()["total"] == 1
        patched = await client.patch(
            f"/api/v1/memories/{memory_id}",
            params={"agent_id": "default"},
            json={"tags": ["goal"]},
        )
        assert patched.json()["tags"] == ["goal"]
        deleted = await client.delete(f"/api/v1/memories/{memory_id}", params={"agent_id": "default"})
        assert deleted.json()["deleted"] is True


@pytest.mark.asyncio
async def test_bulk_delete_requires_filter(memory_api):
    app, _, _ = memory_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/memories",
            json={"agent_id": "default", "content": "待删除记忆", "scope": "agent"},
        )
        bad = await client.post("/api/v1/memories/bulk-delete", json={"agent_id": "default"})
        assert bad.status_code == 400
        ok = await client.post(
            "/api/v1/memories/bulk-delete",
            json={"agent_id": "default", "status": "active"},
        )
        assert ok.json()["deleted"] >= 1


def test_restart_persistence(memory_env):
    repo, service = memory_env
    saved = service.create_manual(agent_id="default", content="重启后仍可检索")
    repo.close()
    service.close()
    service.initialize()
    loaded = service.get("default", saved.id)
    assert loaded is not None
    assert loaded.content == "重启后仍可检索"


@pytest.mark.asyncio
async def test_chat_injects_memory_block(memory_api):
    app, fake_agent, service = memory_api
    service.create_manual(agent_id="default", content="用户偏好：简洁回答")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/agent/chat",
            json={"message": "请简洁回答并总结", "agent_id": "default", "thread_id": "thread-x"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["memory_context"]["used_count"] >= 1
        state = fake_agent.calls[-1]["state"]
        content = state["messages"][0]["content"]
        assert "用户记忆" in content
        assert "非系统指令" in content
