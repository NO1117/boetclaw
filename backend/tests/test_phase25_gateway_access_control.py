"""Phase 25 tests: gateway channel access control."""

from typing import Any


class _AccessChannel:
    channel = "fake"
    render_style = type("Style", (), {"value": "plain"})()

    def is_configured(self) -> bool:
        return True

    async def parse_incoming(self, payload: dict[str, Any]):
        from app.services.gateway.base import GatewayMessage

        return GatewayMessage(
            platform="fake",
            user_id=str(payload.get("user_id", "")),
            user_name=str(payload.get("user_name", "")),
            content=str(payload.get("content", "")),
            message_id=str(payload.get("message_id", "m1")),
            chat_id=str(payload.get("chat_id", "c1")),
            raw=payload,
        )

    async def send_reply(self, message, content: str):
        return None


def test_gateway_access_control_api_persists(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.gateway.access_control import access_control_store

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)

    client = TestClient(app)
    res = client.put("/api/v1/gateway/access-control", json={"channels": {"fake": {"allowed_users": ["u1", ""]}}})
    assert res.status_code == 200
    assert res.json()["channels"]["fake"]["allowed_users"] == ["u1"]

    res = client.get("/api/v1/gateway/access-control")
    assert res.status_code == 200
    assert res.json()["channels"]["fake"]["allowed_users"] == ["u1"]


def test_gateway_webhook_denies_unlisted_user(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.gateway.access_control import access_control_store
    from app.services.gateway.manager import channel_manager

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({"fake": {"allowed_users": ["u1"]}})
    monkeypatch.setattr(channel_manager, "_channels", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_queues", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_consumers", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_history", [], raising=False)
    channel_manager.register(_AccessChannel())

    client = TestClient(app)
    res = client.post("/api/v1/gateway/fake/webhook", json={"user_id": "u2", "content": "blocked"})

    assert res.status_code == 200
    assert res.json()["message"] == "Denied by access control"
    assert channel_manager.queue_size("fake") == 0
    history = channel_manager.message_history(platform="fake", status="denied")
    assert history[0]["user_id"] == "u2"
    assert history[0]["detail"] == "user_not_allowed"


def test_gateway_webhook_allows_listed_user(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.gateway.access_control import access_control_store
    from app.services.gateway.manager import channel_manager

    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({"fake": {"allowed_users": ["u1"]}})
    monkeypatch.setattr(channel_manager, "_channels", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_queues", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_consumers", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_history", [], raising=False)
    channel_manager.register(_AccessChannel())

    client = TestClient(app)
    res = client.post("/api/v1/gateway/fake/webhook", json={"user_id": "u1", "content": "allowed"})

    assert res.status_code == 200
    assert res.json()["message"] == "Task queued"
    assert channel_manager.queue_size("fake") == 1


def test_gateway_webhook_rate_limits_user(monkeypatch, tmp_path):
    from collections import defaultdict, deque

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.services.gateway.access_control import access_control_store
    from app.services.gateway.manager import channel_manager

    monkeypatch.setattr(settings, "gateway_rate_limit_per_minute", 1, raising=False)
    monkeypatch.setattr(access_control_store, "path", tmp_path / "access_control.json", raising=False)
    access_control_store.update({})
    monkeypatch.setattr(channel_manager, "_channels", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_queues", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_consumers", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_history", [], raising=False)
    monkeypatch.setattr(channel_manager, "_rate_hits", defaultdict(deque), raising=False)
    monkeypatch.setattr(channel_manager, "history_path", tmp_path / "gateway" / "message_history.json", raising=False)
    channel_manager.register(_AccessChannel())

    client = TestClient(app)
    first = client.post("/api/v1/gateway/fake/webhook", json={"user_id": "u1", "content": "first"})
    second = client.post("/api/v1/gateway/fake/webhook", json={"user_id": "u1", "content": "second"})

    assert first.status_code == 200
    assert first.json()["message"] == "Task queued"
    assert second.status_code == 200
    assert second.json()["message"] == "Rate limited"
    assert channel_manager.queue_size("fake") == 1
    history = channel_manager.message_history(platform="fake", status="rate_limited")
    assert history[0]["user_id"] == "u1"
    assert history[0]["detail"] == "user_rate_limit"
