"""Phase 15.4 tests: gateway operations API."""

from typing import Any


class _FakeChannel:
    channel = "fake"
    render_style = type("Style", (), {"value": "plain"})()

    def is_configured(self) -> bool:
        return True

    async def parse_incoming(self, payload: dict[str, Any]):
        return None

    async def send_reply(self, message, content: str):
        return None


def test_gateway_status_history_and_retry(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.gateway.base import GatewayMessage
    from app.services.gateway.manager import channel_manager

    monkeypatch.setattr(channel_manager, "_channels", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_queues", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_consumers", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_history", [], raising=False)
    monkeypatch.setattr(channel_manager, "history_path", tmp_path / "gateway" / "message_history.json", raising=False)
    channel_manager.register(_FakeChannel())

    msg = GatewayMessage(
        platform="fake",
        user_id="u1",
        user_name="User",
        content="hello",
        message_id="m1",
        chat_id="c1",
    )
    record = channel_manager.record_message("fake", msg, "failed", "boom")

    client = TestClient(app)
    res = client.get("/api/v1/gateway/status")
    assert res.status_code == 200
    assert res.json()["channels"][0]["name"] == "fake"
    assert res.json()["channels"][0]["queue_depth"] == 0

    res = client.get("/api/v1/gateway/messages?platform=fake&status=failed")
    assert res.status_code == 200
    assert res.json()["messages"][0]["detail"] == "boom"

    res = client.post(f"/api/v1/gateway/messages/{record['id']}/retry")
    assert res.status_code == 200
    assert channel_manager.queue_size("fake") == 1


def test_gateway_message_history_persists(tmp_path):
    from app.services.gateway.base import GatewayMessage
    from app.services.gateway.manager import ChannelManager

    history_path = tmp_path / "gateway" / "message_history.json"
    manager = ChannelManager(history_path=history_path)
    msg = GatewayMessage(
        platform="fake",
        user_id="u1",
        user_name="User",
        content="hello",
        message_id="m1",
        chat_id="c1",
    )

    record = manager.record_message("fake", msg, "failed", "boom", task_id="t1", trace_id="tr1")
    assert history_path.exists()
    assert "_message" not in history_path.read_text(encoding="utf-8")

    restored = ChannelManager(history_path=history_path)
    rows = restored.message_history(platform="fake", status="failed")
    assert len(rows) == 1
    assert rows[0]["id"] == record["id"]
    assert rows[0]["detail"] == "boom"
    assert rows[0]["task_id"] == "t1"
    assert rows[0]["trace_id"] == "tr1"
    assert restored.retry_message(record["id"]) is False


def test_gateway_enqueue_rate_limit(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.gateway.base import GatewayMessage
    from app.services.gateway.manager import ChannelManager

    monkeypatch.setattr(settings, "gateway_rate_limit_per_minute", 1, raising=False)
    manager = ChannelManager(history_path=tmp_path / "gateway" / "message_history.json")
    manager.register(_FakeChannel())
    msg1 = GatewayMessage(platform="fake", user_id="u1", user_name="User", content="one", message_id="m1", chat_id="c1")
    msg2 = GatewayMessage(platform="fake", user_id="u1", user_name="User", content="two", message_id="m2", chat_id="c1")

    assert manager.enqueue("fake", msg1) is True
    assert manager.enqueue("fake", msg2) is False

    rows = manager.message_history(platform="fake", status="rate_limited")
    assert len(rows) == 1
    assert rows[0]["detail"] == "user_rate_limit"
    assert manager.queue_size("fake") == 1
