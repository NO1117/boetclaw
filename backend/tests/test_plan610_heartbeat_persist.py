"""PLAN-610: Heartbeat config persistence and reschedule."""

from __future__ import annotations

import pytest


def test_heartbeat_update_persists_to_env(tmp_path, monkeypatch):
    from app.core import config as config_module
    from app.services.heartbeat import HeartbeatService

    env_path = tmp_path / ".env"
    env_path.write_text("HEARTBEAT_ENABLED=false\nOTHER=keep\n", encoding="utf-8")
    monkeypatch.setattr(config_module.settings, "heartbeat_enabled", False)
    monkeypatch.setattr(config_module.settings, "heartbeat_interval_minutes", 30)
    monkeypatch.setattr(config_module.settings, "heartbeat_prompt", "old")

    svc = HeartbeatService(env_path=env_path)
    result = svc.update(enabled=True, interval_minutes=5, prompt="health check", persist=True)

    assert result["enabled"] is True
    assert result["interval_minutes"] == 5
    assert result["prompt"] == "health check"
    assert result["persisted"] is True
    text = env_path.read_text(encoding="utf-8")
    assert "HEARTBEAT_ENABLED=true" in text
    assert "HEARTBEAT_INTERVAL_MINUTES=5" in text
    assert "HEARTBEAT_PROMPT=" in text
    assert "health check" in text
    assert "OTHER=keep" in text


def test_heartbeat_update_reschedules_and_disables(tmp_path, monkeypatch):
    from app.core import config as config_module
    from app.services.heartbeat import HeartbeatService

    monkeypatch.setattr(config_module.settings, "heartbeat_enabled", True)
    monkeypatch.setattr(config_module.settings, "heartbeat_interval_minutes", 10)
    monkeypatch.setattr(config_module.settings, "heartbeat_prompt", "ping")

    calls: list[tuple[str, dict]] = []

    class FakeScheduler:
        def add_job(self, *args, **kwargs):
            calls.append(("add", kwargs))

        def remove_job(self, job_id):
            calls.append(("remove", {"id": job_id}))

    svc = HeartbeatService(env_path=tmp_path / ".env")
    svc.start(FakeScheduler())
    assert any(kind == "add" for kind, _ in calls)

    calls.clear()
    svc.update(enabled=False, persist=True)
    assert ("remove", {"id": "heartbeat"}) in calls
    assert not any(kind == "add" for kind, _ in calls)

    calls.clear()
    svc.update(enabled=True, interval_minutes=2, persist=False)
    assert any(kind == "add" and item.get("minutes") == 2 for kind, item in calls)


@pytest.mark.asyncio
async def test_heartbeat_route_uses_service_update(monkeypatch):
    from app.api.routes import cron as cron_routes
    from app.api.schemas import HeartbeatUpdateRequest

    captured = {}

    def fake_update(**kwargs):
        captured.update(kwargs)
        return {"enabled": True, "interval_minutes": 7, "prompt": "x", "persisted": True}

    monkeypatch.setattr(cron_routes.heartbeat_service, "update", fake_update)
    result = await cron_routes.update_heartbeat(
        HeartbeatUpdateRequest(enabled=True, interval_minutes=7, prompt="x")
    )
    assert captured["enabled"] is True
    assert captured["interval_minutes"] == 7
    assert captured["prompt"] == "x"
    assert captured["persist"] is True
    assert result["persisted"] is True
