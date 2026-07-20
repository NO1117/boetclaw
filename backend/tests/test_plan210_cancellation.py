"""PLAN-210: real cancellation for tasks, slash commands, and Agent runs."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture(autouse=True)
async def clean_run_registry():
    from app.services.run_registry import run_registry

    await run_registry.shutdown()
    run_registry.clear()
    yield
    await run_registry.shutdown()
    run_registry.clear()


@pytest.fixture
def cancellation_app(tmp_path, monkeypatch):
    from app.api.routes import agent as agent_routes
    from app.api.routes import tasks as task_routes
    from app.services.task_scheduler import TaskScheduler

    scheduler = TaskScheduler(tmp_path / "tasks.json")
    monkeypatch.setattr(task_routes, "task_scheduler", scheduler)
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/v1")
    app.include_router(task_routes.router, prefix="/api/v1")
    return app, scheduler, task_routes


@pytest.mark.asyncio
async def test_task_cancel_reaches_agent_and_terminal_status_is_not_overwritten(
    cancellation_app,
    monkeypatch,
):
    app, scheduler, task_routes = cancellation_app
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_invoke(*_args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {
            "response": "must not complete",
            "trace_id": kwargs["trace_id"],
            "run_id": kwargs["run_id"],
        }

    monkeypatch.setattr(task_routes.agent_manager, "invoke", long_invoke)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/tasks",
            json={"title": "long", "prompt": "wait", "auto_run": True},
        )
        task_id = created.json()["id"]
        await asyncio.wait_for(started.wait(), timeout=1)
        response = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        repeated = await client.post(f"/api/v1/tasks/{task_id}/cancel")

    assert response.status_code == 200
    assert repeated.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert cancelled.is_set()
    task = scheduler.get(task_id)
    assert task is not None
    assert task.status.value == "cancelled"
    assert task.result == ""


@pytest.mark.asyncio
async def test_completed_task_cancel_is_explicit(cancellation_app):
    from app.services.task_scheduler import TaskStatus

    app, scheduler, _ = cancellation_app
    task = scheduler.create("done", "done")
    scheduler.update_status(task.id, TaskStatus.COMPLETED, result="ok")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/v1/tasks/{task.id}/cancel")

    assert response.status_code == 409
    assert "already completed" in response.text


@pytest.mark.asyncio
async def test_stop_targets_same_agent_and_thread_only(cancellation_app):
    from app.services.run_registry import RunStatus, run_registry

    app, _, _ = cancellation_app

    async def wait_forever():
        await asyncio.Event().wait()

    first = run_registry.start(
        wait_forever(),
        agent_id="agent-a",
        thread_id="shared-thread",
        run_id="run-a",
    )
    second = run_registry.start(
        wait_forever(),
        agent_id="agent-b",
        thread_id="shared-thread",
        run_id="run-b",
    )
    await asyncio.sleep(0)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        stopped = await client.post(
            "/api/v1/agent/chat",
            json={"message": "/stop", "agent_id": "agent-a", "thread_id": "shared-thread"},
        )
        no_run = await client.post(
            "/api/v1/agent/chat",
            json={"message": "/stop", "agent_id": "agent-a", "thread_id": "shared-thread"},
        )

    assert stopped.status_code == 200
    assert "确认取消" in stopped.json()["response"]
    assert first.status == RunStatus.CANCELLED
    assert second.status == RunStatus.RUNNING
    assert run_registry.active_for("agent-b", "shared-thread") is second
    assert "没有可停止" in no_run.json()["response"]


@pytest.mark.asyncio
async def test_run_cancel_endpoint_checks_run_agent_and_thread(cancellation_app):
    from app.services.run_registry import RunStatus, run_registry

    app, _, _ = cancellation_app

    async def wait_forever():
        await asyncio.Event().wait()

    entry = run_registry.start(
        wait_forever(),
        agent_id="agent-a",
        thread_id="thread-a",
        run_id="stream-run",
    )
    await asyncio.sleep(0)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        isolated = await client.post(
            "/api/v1/agent/runs/cancel",
            json={"agent_id": "agent-b", "thread_id": "thread-a", "run_id": "stream-run"},
        )
        cancelled = await client.post(
            "/api/v1/agent/runs/cancel",
            json={"agent_id": "agent-a", "thread_id": "thread-a", "run_id": "stream-run"},
        )
        repeated = await client.post(
            "/api/v1/agent/runs/cancel",
            json={"agent_id": "agent-a", "thread_id": "thread-a", "run_id": "stream-run"},
        )

    assert isolated.status_code == 404
    assert cancelled.status_code == 200
    assert repeated.status_code == 200
    assert entry.status == RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_completion_race_keeps_cancelled_terminal_state():
    from app.services.run_registry import RunStatus, run_registry

    release = asyncio.Event()

    async def racing_run():
        await release.wait()
        return "done"

    entry = run_registry.start(
        racing_run(),
        agent_id="default",
        thread_id="race-thread",
        run_id="race-run",
    )
    await asyncio.sleep(0)
    cancel_task = asyncio.create_task(run_registry.cancel(run_id="race-run"))
    release.set()
    result = await cancel_task

    assert result.cancelled
    assert entry.status == RunStatus.CANCELLED
    assert not run_registry.transition(entry, RunStatus.COMPLETED)


@pytest.mark.asyncio
async def test_plan_interrupt_finishes_normally_in_registry(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessageChunk

    from app.api.routes.agent import router
    from app.memory.plan_history_store import plan_history_store
    from app.services import chat_orchestration
    from app.services.execution_resume import graph_resume_adapter
    from app.services.run_registry import RunStatus, run_registry

    class PlanAgent:
        async def astream(self, *_args, **_kwargs):
            yield ("", "messages", (AIMessageChunk(content="plan"), {}))
            yield ("", "updates", {"planner": {"todos": ["step"]}})
            yield (
                "",
                "updates",
                {"__interrupt__": [{"id": "interrupt-1", "value": {"type": "plan_confirm"}}]},
            )

    agent = PlanAgent()

    async def resolve(_agent_id: str):
        return agent

    monkeypatch.setattr(chat_orchestration, "resolve_agent_graph", resolve)
    monkeypatch.setattr(plan_history_store, "path", tmp_path / "plans.json")
    monkeypatch.setattr(graph_resume_adapter, "register", lambda *_: None)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={
                "message": "/plan drill",
                "thread_id": "plan-not-cancelled",
                "agent_id": "planner",
            },
        )

    run_id = re.search(r'"run_id"\s*:\s*"([^"]+)"', response.text).group(1)  # type: ignore[union-attr]
    entry = run_registry.get(run_id)
    assert entry is not None
    assert entry.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_registry_shutdown_cleans_active_runs():
    from app.services.run_registry import run_registry

    async def wait_forever():
        await asyncio.Event().wait()

    entry = run_registry.start(
        wait_forever(),
        agent_id="default",
        thread_id="shutdown-thread",
        run_id="shutdown-run",
    )
    await asyncio.sleep(0)
    await run_registry.shutdown()
    assert entry.status.value == "cancelled"
    assert run_registry.active_for("default", "shutdown-thread") is None
    with suppress(asyncio.CancelledError):
        if entry.task:
            await entry.task
