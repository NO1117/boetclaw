"""Phase 12 tests: trace persistence, timeline, OTel setup."""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_trace_store_persist_roundtrip():
    from app.core.observability import EventType, TraceEvent, TraceStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "traces.jsonl"
        store = TraceStore(max_events=100, persist_path=path, persist_enabled=True)
        ev = TraceEvent(
            id="e1",
            trace_id="t1",
            run_id="r1",
            event_type=EventType.AGENT_START,
            timestamp="2026-01-01T00:00:00+00:00",
            data={"source": "user"},
        )
        store.add(ev)

        store2 = TraceStore(max_events=100, persist_path=path, persist_enabled=True)
        assert len(store2.get_by_trace("t1")) == 1
        assert store2.get_by_trace("t1")[0].event_type == EventType.AGENT_START


def test_build_timeline_categories():
    from app.core.observability import EventType, TraceEvent, TraceStore
    from app.core import timeline as tl_mod

    store = TraceStore(persist_enabled=False)
    tid = "trace-abc"
    rid = "run-xyz"
    for idx, (et, data) in enumerate([
        (EventType.AGENT_START, {"source": "user"}),
        (EventType.PLAN_CREATED, {}),
        (EventType.TOOL_CALL, {"tool": "write_todos"}),
        (EventType.GUARD_BLOCK, {"tool": "execute_shell_command"}),
        (EventType.AGENT_END, {}),
    ]):
        store.add(
            TraceEvent(
                id=f"id-{et.value}",
                trace_id=tid,
                run_id=rid,
                event_type=et,
                timestamp=f"2026-01-01T00:00:0{idx}+00:00",
                data=data,
            )
        )

    original = tl_mod.trace_store
    tl_mod.trace_store = store
    try:
        result = tl_mod.build_timeline(tid)
    finally:
        tl_mod.trace_store = original

    assert result["event_count"] == 5
    assert result["duration_ms"] == 4000
    assert result["categories"]["plan"] >= 1
    assert result["categories"]["tool"] >= 1
    assert result["categories"]["guard"] >= 1
    assert result["events"][0]["sequence"] == 1
    assert result["events"][1]["delta_ms"] == 1000
    assert any(e["category"] == "agent" for e in result["events"])


def test_timeline_api_404_and_ok():
    from app.core.observability import EventType, emit_event, trace_store
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/v1/monitor/trace/nope/timeline").status_code == 404

    ev = emit_event(EventType.AGENT_START, {"message": "hi"}, trace_id="apitrace1")
    resp = client.get(f"/api/v1/monitor/trace/{ev.trace_id}/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == ev.trace_id
    assert body["event_count"] >= 1


def test_otel_setup_idempotent():
    from app.core import otel as otel_mod
    from app.core.config import settings
    from app.main import app

    # main.py already initialized OTel at import time
    assert settings.otel_console_exporter is False
    assert otel_mod._instrumented is True
    otel_mod.setup_otel(app)  # second call should no-op
    assert otel_mod._instrumented is True


def test_monitor_metrics_prometheus_text(monkeypatch, tmp_path):
    import asyncio

    from app.core.observability import EventType, emit_event, trace_store
    from app.main import app
    from app.services.gateway.base import GatewayMessage
    from app.services.gateway.channels.qq import QQChannel
    from app.services.gateway.manager import channel_manager
    from app.services.task_scheduler import TaskStatus, task_scheduler
    from app.tools.mcp_manager import mcp_manager

    monkeypatch.setattr(task_scheduler, "_tasks", {}, raising=False)
    monkeypatch.setattr(task_scheduler, "store_path", tmp_path / "task_history.json", raising=False)
    monkeypatch.setattr(channel_manager, "_channels", {}, raising=False)
    monkeypatch.setattr(channel_manager, "_queues", {}, raising=False)
    monkeypatch.setattr(mcp_manager, "_recover_counts", {"success": 2, "failed": 1}, raising=False)
    monkeypatch.setattr(trace_store, "_events", [], raising=False)
    channel_manager.register(QQChannel())
    channel_manager._queues["qq"] = asyncio.Queue(maxsize=5)
    channel_manager.enqueue(
        "qq",
        GatewayMessage(platform="qq", user_id="u1", user_name="n", content="ping", message_id="m1", chat_id="c1"),
    )
    task = task_scheduler.create("metrics", "ping")
    task_scheduler.update_status(task.id, TaskStatus.COMPLETED)
    emit_event(EventType.AGENT_START, {"thread_id": "metrics-thread"}, trace_id="metrics-trace", run_id="metrics-run")
    emit_event(EventType.AGENT_END, {"thread_id": "metrics-thread"}, trace_id="metrics-trace", run_id="metrics-run")
    emit_event(EventType.TOOL_CALL, {"tool": "x"}, trace_id="metrics-trace")
    emit_event(EventType.TOOL_RESULT, {"tool": "x"}, trace_id="metrics-trace")
    emit_event(EventType.GUARD_BLOCK, {"guardian": "path_guard"}, trace_id="metrics-trace")
    emit_event(EventType.PROVIDER_RETRY, {"provider": "openai"}, trace_id="metrics-trace")
    emit_event(EventType.ERROR, {"source": "agent"}, trace_id="metrics-trace")

    client = TestClient(app)
    resp = client.get("/api/v1/monitor/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert 'boetclaw_agent_runs_total{status="started"} 1' in text
    assert 'boetclaw_agent_runs_total{status="completed"} 1' in text
    assert 'boetclaw_agent_runs_total{status="failed"} 1' in text
    assert "# TYPE boetclaw_agent_run_duration_seconds histogram" in text
    assert 'boetclaw_agent_run_duration_seconds_bucket{le="1"} 1' in text
    assert "boetclaw_agent_run_duration_seconds_count 1" in text
    assert "boetclaw_agent_run_duration_seconds_sum" in text
    assert 'boetclaw_tool_calls_total{tool="x",status="started"} 1' in text
    assert 'boetclaw_tool_calls_total{tool="x",status="completed"} 1' in text
    assert 'boetclaw_guard_blocks_total{guardian="path_guard"} 1' in text
    assert 'boetclaw_llm_retries_total{provider="openai"} 1' in text
    assert 'boetclaw_tasks_total{status="completed"} 1' in text
    assert "boetclaw_trace_events_total" in text
    assert 'boetclaw_trace_events_by_type{event_type="tool_call"}' in text
    assert 'boetclaw_gateway_queue_depth{platform="qq"} 1' in text
    assert "boetclaw_approvals_pending" in text
    assert 'boetclaw_mcp_recover_total{result="success"} 2' in text
    assert 'boetclaw_mcp_recover_total{result="failed"} 1' in text


def test_otel_disabled_no_crash(monkeypatch):
    from app.core import otel as otel_mod
    from app.core.config import settings
    from app.main import app

    otel_mod._instrumented = False
    monkeypatch.setattr(settings, "otel_enabled", False, raising=False)
    otel_mod.setup_otel(app)
    assert otel_mod._instrumented is False
