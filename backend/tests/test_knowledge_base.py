"""Knowledge base CRUD, isolation, dedup, retrieval, bindings, and chat integration."""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi import FastAPI

from app.services.attachments.service import attachment_service
from app.services.knowledge_base.service import kb_service
from app.services.knowledge_base.store import kb_store


@pytest.fixture
def kb_api(tmp_path, monkeypatch):
    from app.api.routes import agent as agent_routes
    from app.api.routes import attachments as attachment_routes
    from app.api.routes import knowledge_bases as kb_routes
    from app.core.agent_factory import BoetClawAgentFactory
    from app.core.config import settings
    from app.memory.session_store import session_store
    from app.providers.manager import provider_manager
    from app.services import chat_orchestration
    from app.services.attachments.store import attachment_store

    kb_root = tmp_path / "knowledge_bases"
    att_root = tmp_path / "attachments"
    monkeypatch.setattr(kb_store, "root", kb_root)
    monkeypatch.setattr(attachment_store, "root", att_root)
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setattr(session_store, "root", tmp_path / "sessions")

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
    cached_agent = FakeAgent()

    async def resolve(_agent_id: str):
        return cached_agent

    monkeypatch.setattr(chat_orchestration, "resolve_agent_graph", resolve)
    monkeypatch.setattr(provider_manager, "get_chat_model", lambda *a, **k: "model:fake")
    monkeypatch.setattr(BoetClawAgentFactory, "build", staticmethod(lambda **k: FakeAgent()))

    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/v1")
    app.include_router(attachment_routes.router, prefix="/api/v1")
    app.include_router(kb_routes.router, prefix="/api/v1")
    return app, cached_agent


def _wait_doc_ready(agent_id: str, kb_id: str, doc_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        doc = kb_service.get_document(agent_id, kb_id, doc_id)
        if doc.status in ("ready", "failed"):
            return doc
        time.sleep(0.05)
    return kb_service.get_document(agent_id, kb_id, doc_id)


@pytest.mark.asyncio
async def test_create_kb_and_upload_document(kb_api):
    app, _ = kb_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "测试库", "description": "说明"},
        )
        assert kb_res.status_code == 200
        kb_id = kb_res.json()["knowledge_base_id"]

        content = b"keyword alpha beta unique-term-kb-001"
        upload_res = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/upload",
            files={"files": ("notes.txt", content, "text/plain")},
        )
        assert upload_res.status_code == 200
        doc_id = upload_res.json()["documents"][0]["document_id"]

    doc = _wait_doc_ready("agent-a", kb_id, doc_id)
    assert doc.status == "ready"
    assert doc.summary.chunk_count >= 1


@pytest.mark.asyncio
async def test_agent_isolation_kb_404(kb_api):
    app, _ = kb_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "私有库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        foreign = await client.get(f"/api/v1/agents/agent-b/knowledge-bases/{kb_id}")
        assert foreign.status_code == 404
        assert "私有" not in foreign.text


@pytest.mark.asyncio
async def test_sha256_dedup_same_blob(kb_api):
    app, _ = kb_api
    transport = httpx.ASGITransport(app=app)
    content = b"dedup-content-same-hash-kb-test"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "去重库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        r1 = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/upload",
            files={"files": ("a.txt", content, "text/plain")},
        )
        r2 = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/upload",
            files={"files": ("b.txt", content, "text/plain")},
        )
        doc1 = r1.json()["documents"][0]
        doc2 = r2.json()["documents"][0]
        assert doc1["document_id"] != doc2["document_id"]
        internal1 = kb_service.get_document("agent-a", kb_id, doc1["document_id"])
        internal2 = kb_service.get_document("agent-a", kb_id, doc2["document_id"])
        assert internal1.sha256 == internal2.sha256


@pytest.mark.asyncio
async def test_archive_restore_delete_purge(kb_api):
    app, _ = kb_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "生命周期库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/archive",
        )
        restored = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/restore",
        )
        assert restored.json()["status"] == "active"
        await client.delete(f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}")
        deleted_get = await client.get(f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}")
        assert deleted_get.status_code == 404
        purge = await client.post(f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/purge")
        assert purge.status_code == 200


@pytest.mark.asyncio
async def test_bind_and_chat_with_kb_citations(kb_api):
    app, fake_agent = kb_api
    transport = httpx.ASGITransport(app=app)
    content = b"retrieval-keyword-zeta unique-kb-chat-term"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "检索库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        up = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/upload",
            files={"files": ("doc.txt", content, "text/plain")},
        )
        doc_id = up.json()["documents"][0]["document_id"]

    doc = _wait_doc_ready("agent-a", kb_id, doc_id)
    assert doc.status == "ready"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/api/v1/agents/agent-a/knowledge-base-bindings/{kb_id}",
            json={"enabled_by_default": True},
        )
        chat_res = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "请说明 retrieval-keyword-zeta",
                "agent_id": "agent-a",
                "knowledge_base_ids": [kb_id],
            },
        )
        assert chat_res.status_code == 200
        body = chat_res.json()
        assert body.get("knowledge_citations")
        assert fake_agent.calls
        user_content = fake_agent.calls[-1]["state"]["messages"][0]["content"]
        assert "retrieval-keyword-zeta" in user_content


@pytest.mark.asyncio
async def test_empty_kb_ids_disables_retrieval(kb_api):
    app, fake_agent = kb_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "默认库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/upload",
            files={"files": ("x.txt", b"secret-kb-content-xyz", "text/plain")},
        )
        await client.post(
            f"/api/v1/agents/agent-a/knowledge-base-bindings/{kb_id}",
            json={"enabled_by_default": True},
        )
        fake_agent.calls.clear()
        chat_res = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "secret-kb-content-xyz",
                "agent_id": "agent-a",
                "knowledge_base_ids": [],
            },
        )
        assert chat_res.status_code == 200
        user_content = fake_agent.calls[-1]["state"]["messages"][0]["content"]
        assert "secret-kb-content-xyz" not in user_content or user_content.strip() == "secret-kb-content-xyz"


@pytest.mark.asyncio
async def test_snippet_preview(kb_api):
    app, _ = kb_api
    transport = httpx.ASGITransport(app=app)
    content = b"preview-snippet-text-here"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "预览库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        up = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/upload",
            files={"files": ("p.txt", content, "text/plain")},
        )
        doc_id = up.json()["documents"][0]["document_id"]

    doc = _wait_doc_ready("agent-a", kb_id, doc_id)
    assert doc.status == "ready"
    chunks = kb_store.load_blob_chunks("agent-a", doc.sha256)
    chunk_id = chunks[0].chunk_id

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        preview = await client.get(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/{doc_id}/preview",
            params={"chunk_id": chunk_id},
        )
        assert preview.status_code == 200
        assert "preview-snippet" in preview.json()["text"]


@pytest.mark.asyncio
async def test_add_from_attachment(kb_api):
    app, _ = kb_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        att = await client.post(
            "/api/v1/agents/agent-a/attachments",
            files={"file": ("from-att.txt", b"attachment-import-kb-content", "text/plain")},
        )
        att_id = att.json()["attachment_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rec = attachment_service.get_record("agent-a", att_id)
            if rec and rec.status in ("ready", "failed"):
                break
            time.sleep(0.05)

        kb_res = await client.post(
            "/api/v1/agents/agent-a/knowledge-bases",
            json={"name": "附件导入库"},
        )
        kb_id = kb_res.json()["knowledge_base_id"]
        add = await client.post(
            f"/api/v1/agents/agent-a/knowledge-bases/{kb_id}/documents/from-attachments",
            json={"attachment_ids": [att_id]},
        )
        assert add.status_code == 200
        doc = add.json()["documents"][0]
        assert doc["source_attachment_id"] == att_id
