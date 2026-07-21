"""Tests for attachment upload, isolation, parsing, lifecycle, and chat integration."""

from __future__ import annotations

import io
import time
import zipfile
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.services.attachments.cleanup import collect_referenced_attachment_ids
from app.services.attachments.service import attachment_service
from app.services.chat_attachments import MAX_FILE_BYTES


def _make_docx_bytes(text: str = "Hello DOCX") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        zf.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


@pytest.fixture
def attachment_api(tmp_path, monkeypatch):
    from app.api.routes import agent as agent_routes
    from app.api.routes import attachments as attachment_routes
    from app.core.agent_factory import BoetClawAgentFactory
    from app.core.config import settings
    from app.memory.session_store import session_store
    from app.providers.manager import provider_manager
    from app.services import chat_orchestration
    from app.services.attachments.store import attachment_store

    store_root = tmp_path / "attachments"
    monkeypatch.setattr(attachment_store, "root", store_root)
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
    return app, store_root, cached_agent


class _ChunkedUploadReader:
    """Simulates a streaming multipart body for httpx uploads."""

    def __init__(self, total_bytes: int, chunk_size: int = 64 * 1024) -> None:
        self._remaining = total_bytes
        self._chunk_size = chunk_size

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0:
            size = self._chunk_size
        take = min(size, self._remaining, self._chunk_size)
        self._remaining -= take
        return b"x" * take


def _wait_ready(agent_id: str, attachment_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = attachment_service.get_record(agent_id, attachment_id)
        assert record is not None
        if record.status in ("ready", "failed"):
            return record
        time.sleep(0.05)
    return attachment_service.get_record(agent_id, attachment_id)


@pytest.mark.asyncio
async def test_oversized_streamed_upload_rejected_before_storage(attachment_api, monkeypatch):
    app, store_root, _ = attachment_api
    upload_mock = AsyncMock()
    monkeypatch.setattr(attachment_service, "upload", upload_mock)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file": (
                "big.bin",
                _ChunkedUploadReader(MAX_FILE_BYTES + 1),
                "application/octet-stream",
            )
        }
        response = await client.post("/api/v1/agents/default/attachments", files=files)
    assert response.status_code == 400
    assert "25 MB" in response.json()["detail"]
    upload_mock.assert_not_called()
    assert list(store_root.glob("default/*/meta.json")) == []


@pytest.mark.asyncio
async def test_upload_at_max_file_bytes_boundary_accepted(attachment_api):
    app, _, _ = attachment_api
    payload = b"a" * MAX_FILE_BYTES
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("boundary.txt", payload, "text/plain")}
        response = await client.post("/api/v1/agents/default/attachments", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["attachment_id"]
    assert body["size"] == MAX_FILE_BYTES
    record = attachment_service.get_record("default", body["attachment_id"])
    assert record is not None
    assert record.size == MAX_FILE_BYTES
    assert record.status != "deleted"


@pytest.mark.asyncio
async def test_upload_text_attachment_reaches_ready(attachment_api):
    app, _, _ = attachment_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("notes.txt", b"keyword alpha beta", "text/plain")}
        response = await client.post("/api/v1/agents/default/attachments", files=files)
    assert response.status_code == 200
    body = response.json()
    attachment_id = body["attachment_id"]
    record = _wait_ready("default", attachment_id)
    assert record.status == "ready"
    assert record.scan_status == "unscanned"


@pytest.mark.asyncio
async def test_agent_isolation_returns_404(attachment_api):
    app, _, _ = attachment_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("secret.txt", b"hidden", "text/plain")}
        upload = await client.post("/api/v1/agents/agent-a/attachments", files=files)
        attachment_id = upload.json()["attachment_id"]
        _wait_ready("agent-a", attachment_id)
        cross = await client.get(f"/api/v1/agents/agent-b/attachments/{attachment_id}")
    assert cross.status_code == 404


@pytest.mark.asyncio
async def test_invalid_path_rejected_without_artifact(attachment_api):
    app, store_root, _ = attachment_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("bad.txt", b"x", "text/plain")}
        data = {"relative_path": "../etc/passwd"}
        response = await client.post("/api/v1/agents/default/attachments", files=files, data=data)
    assert response.status_code == 400
    assert list(store_root.glob("default/*/meta.json")) == []


@pytest.mark.asyncio
async def test_chat_with_attachment_ids(attachment_api):
    app, _, cached_agent = attachment_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("report.txt", b"find keyword needle here", "text/plain")}
        upload = await client.post("/api/v1/agents/default/attachments", files=files)
        attachment_id = upload.json()["attachment_id"]
        _wait_ready("default", attachment_id)
        chat = await client.post(
            "/api/v1/agent/chat",
            json={"message": "needle", "attachment_ids": [attachment_id], "agent_id": "default"},
        )
    assert chat.status_code == 200
    assert cached_agent.calls
    content = cached_agent.calls[-1]["state"]["messages"][0]["content"]
    assert "needle" in content


@pytest.mark.asyncio
async def test_delete_tombstones_and_removes_files(attachment_api):
    app, store_root, _ = attachment_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("gone.txt", b"bye", "text/plain")}
        upload = await client.post("/api/v1/agents/default/attachments", files=files)
        attachment_id = upload.json()["attachment_id"]
        _wait_ready("default", attachment_id)
        delete = await client.delete(f"/api/v1/agents/default/attachments/{attachment_id}")
        assert delete.status_code == 200
        get_resp = await client.get(f"/api/v1/agents/default/attachments/{attachment_id}")
    assert get_resp.status_code == 404
    tombstone_path = store_root / "default" / "tombstones.json"
    assert tombstone_path.exists()


@pytest.mark.asyncio
async def test_retry_failed_parse(attachment_api, monkeypatch):
    app, _, _ = attachment_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("broken.txt", b"data", "text/plain")}
        upload = await client.post("/api/v1/agents/default/attachments", files=files)
        attachment_id = upload.json()["attachment_id"]
        _wait_ready("default", attachment_id)

        from app.services.attachments.store import attachment_store

        record = attachment_service.get_record("default", attachment_id)
        assert record is not None
        record.status = "failed"
        record.error_summary = "simulated parser failure"
        attachment_store.save_record(record)

        retry = await client.post(f"/api/v1/agents/default/attachments/{attachment_id}/retry")
        assert retry.status_code == 200
        record = _wait_ready("default", attachment_id)
        assert record.status == "ready"


def test_cleanup_skips_referenced_attachment(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "t1.json").write_text(
        '{"messages":[{"role":"user","attachment_refs":["att-1"]}]}',
        encoding="utf-8",
    )
    referenced = collect_referenced_attachment_ids(sessions)
    assert "att-1" in referenced


@pytest.mark.asyncio
async def test_docx_upload_attempt(attachment_api):
    pytest.importorskip("docx")
    app, _, _ = attachment_api
    data = _make_docx_bytes("Section content")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file": (
                "sample.docx",
                data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        upload = await client.post("/api/v1/agents/default/attachments", files=files)
        attachment_id = upload.json()["attachment_id"]
        record = _wait_ready("default", attachment_id)
    assert record.status in ("ready", "failed")
