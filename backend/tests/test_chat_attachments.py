"""Tests for multimodal chat attachments and per-request model overrides."""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.services.chat_attachments import (
    AttachmentValidationError,
    ChatAttachmentInput,
    prepare_attachment_content,
)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        from langchain_core.messages import AIMessage

        self.calls.append({"state": state, "config": config})
        return {"messages": [AIMessage(content="ok")], "todos": []}

    async def astream(self, state: dict[str, Any], config: dict[str, Any], **_: Any):
        from langchain_core.messages import AIMessageChunk

        self.calls.append({"state": state, "config": config})
        yield ("", "messages", (AIMessageChunk(content="ok"), {}))


@pytest.fixture
def attachment_app(tmp_path, monkeypatch):
    from app.api.routes.agent import router
    from app.core.agent_factory import BoetClawAgentFactory
    from app.core.config import settings
    from app.memory.session_store import session_store
    from app.providers.manager import provider_manager
    from app.services import chat_orchestration

    from app.core.checkpoint import checkpoint_provider

    cached_agent = FakeAgent()
    override_agents: list[FakeAgent] = []
    factory_builds: list[dict[str, Any]] = []
    get_model_calls: list[str] = []

    async def resolve(_agent_id: str):
        return cached_agent

    async def fake_checkpoint(_agent_id: str):
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()

    def tracking_get_chat_model(model_string: str | None = None, **kwargs: Any):
        resolved = model_string or settings.model_string
        get_model_calls.append(resolved)
        return f"model:{resolved}"

    def tracking_build(**kwargs: Any):
        factory_builds.append(dict(kwargs))
        override = FakeAgent()
        override_agents.append(override)
        return override

    monkeypatch.setattr(chat_orchestration, "resolve_agent_graph", resolve)
    monkeypatch.setattr(checkpoint_provider, "get", fake_checkpoint)
    monkeypatch.setattr(provider_manager, "get_chat_model", tracking_get_chat_model)
    monkeypatch.setattr(BoetClawAgentFactory, "build", staticmethod(tracking_build))
    monkeypatch.setattr(session_store, "root", tmp_path / "sessions")

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app, cached_agent, override_agents, factory_builds, get_model_calls, settings


def test_prepare_text_attachment_includes_decoded_content():
    prepared = prepare_attachment_content(
        "请阅读",
        [
            ChatAttachmentInput(
                filename="notes.txt",
                mime_type="text/plain",
                size=5,
                kind="text",
                content_base64=_b64("hello"),
            )
        ],
    )
    assert isinstance(prepared.user_content, str)
    assert "hello" in prepared.user_content
    assert prepared.summaries[0].kind == "text"


def test_prepare_image_attachment_builds_multimodal_blocks():
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    prepared = prepare_attachment_content(
        "",
        [
            ChatAttachmentInput(
                filename="dot.png",
                mime_type="image/png",
                size=len(png),
                kind="image",
                content_base64=base64.b64encode(png).decode("ascii"),
            )
        ],
    )
    assert isinstance(prepared.user_content, list)
    assert prepared.user_content[0]["type"] == "image_url"
    assert prepared.has_images is True


def test_reject_oversized_attachment():
    with pytest.raises(AttachmentValidationError):
        prepare_attachment_content(
            "",
            [
                ChatAttachmentInput(
                    filename="big.bin",
                    mime_type="application/octet-stream",
                    size=26 * 1024 * 1024,
                    kind="binary",
                    content_base64=_b64("x"),
                )
            ],
        )


def test_reject_invalid_base64():
    with pytest.raises(AttachmentValidationError):
        prepare_attachment_content(
            "",
            [
                ChatAttachmentInput(
                    filename="bad.txt",
                    mime_type="text/plain",
                    size=3,
                    kind="text",
                    content_base64="***",
                )
            ],
        )


@pytest.mark.asyncio
async def test_backward_compatible_text_request(attachment_app):
    app, cached_agent, _, _, _, _ = attachment_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={"message": "hello"},
        )
    assert response.status_code == 200
    assert cached_agent.calls
    assert cached_agent.calls[0]["state"]["messages"][0]["content"] == "hello"


@pytest.mark.asyncio
async def test_attachment_only_request(attachment_app):
    app, cached_agent, _, _, _, _ = attachment_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "",
                "attachments": [
                    {
                        "filename": "readme.md",
                        "mime_type": "text/markdown",
                        "size": 11,
                        "kind": "text",
                        "content_base64": _b64("# Title\n"),
                    }
                ],
            },
        )
    assert response.status_code == 200
    content = cached_agent.calls[-1]["state"]["messages"][0]["content"]
    assert "# Title" in content


@pytest.mark.asyncio
async def test_non_vision_model_rejects_images(attachment_app, monkeypatch):
    from app.core.config import settings

    app, _, _, _, _, settings_obj = attachment_app
    monkeypatch.setattr(settings_obj, "llm_provider", "openai")
    monkeypatch.setattr(settings_obj, "llm_model", "o1")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "看图片",
                "attachments": [
                    {
                        "filename": "dot.png",
                        "mime_type": "image/png",
                        "size": len(png),
                        "kind": "image",
                        "content_base64": base64.b64encode(png).decode("ascii"),
                    }
                ],
            },
        )
    assert response.status_code == 400
    assert "不支持图像" in response.text


@pytest.mark.asyncio
async def test_provider_model_override_without_mutating_defaults(attachment_app, monkeypatch):
    from app.core.config import settings

    app, cached_agent, override_agents, factory_builds, get_model_calls, settings_obj = attachment_app
    cached_before = id(cached_agent)
    before = (settings_obj.llm_provider, settings_obj.llm_model)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={
                "message": "override me",
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        )
    assert response.status_code == 200
    assert "openai:gpt-4o-mini" in get_model_calls
    assert len(factory_builds) == 1
    assert factory_builds[0]["model"] == "model:openai:gpt-4o-mini"
    assert cached_agent.calls == []
    assert len(override_agents) == 1
    assert override_agents[0].calls
    assert override_agents[0].calls[-1]["config"]["configurable"]["model_string"] == "openai:gpt-4o-mini"
    assert id(cached_agent) == cached_before
    after = (settings_obj.llm_provider, settings_obj.llm_model)
    assert before[0] == after[0]
    assert before[1] == after[1]
    assert settings.model_string == f"{settings_obj.llm_provider}:{settings_obj.llm_model}"


@pytest.mark.asyncio
async def test_stream_model_override_uses_fresh_graph(attachment_app):
    app, cached_agent, override_agents, factory_builds, get_model_calls, _ = attachment_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={
                "message": "stream override",
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        )
    assert response.status_code == 200
    assert "openai:gpt-4o-mini" in get_model_calls
    assert len(factory_builds) == 1
    assert cached_agent.calls == []
    assert len(override_agents) == 1
    assert override_agents[0].calls
    assert override_agents[0].calls[-1]["config"]["configurable"]["model_string"] == "openai:gpt-4o-mini"


@pytest.mark.asyncio
async def test_reject_too_many_attachments(attachment_app):
    app, _, _, _, _, _ = attachment_app
    items = [
        {
            "filename": f"f{i}.txt",
            "mime_type": "text/plain",
            "size": 1,
            "kind": "text",
            "content_base64": _b64("a"),
        }
        for i in range(21)
    ]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat",
            json={"message": "", "attachments": items},
        )
    assert response.status_code == 400
