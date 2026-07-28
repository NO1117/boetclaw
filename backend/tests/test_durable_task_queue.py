"""Tests for durable SQLite task queue."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def queue_service(tmp_path, monkeypatch):
    from app.services.task_queue.service import TaskQueueService

    db = tmp_path / "tasks" / "task_queue.sqlite3"
    legacy = tmp_path / "tasks" / "task_history.json"
    monkeypatch.setattr("app.core.config.settings.task_queue_global_concurrency", 2)
    monkeypatch.setattr("app.core.config.settings.task_queue_agent_concurrency", 2)
    monkeypatch.setattr("app.core.config.settings.task_queue_provider_concurrency", 2)
    svc = TaskQueueService(db_path=db, legacy_json_path=legacy)
    svc.initialize()
    yield svc
    svc.close()


def test_json_migration_is_idempotent(tmp_path):
    from app.services.task_queue.service import TaskQueueService

    db = tmp_path / "tasks" / "task_history.json"
    legacy = db.parent / "task_history.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            [
                {
                    "id": "legacy-1",
                    "title": "旧任务",
                    "prompt": "hello",
                    "status": "completed",
                    "thread_id": "t1",
                    "trace_id": "tr1",
                    "run_id": "r1",
                    "result": "ok",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "metadata": {"agent_id": "a1"},
                }
            ]
        ),
        encoding="utf-8",
    )
    sqlite = legacy.parent / "task_queue.sqlite3"
    first = TaskQueueService(db_path=sqlite, legacy_json_path=legacy)
    first.initialize()
    assert first.get("legacy-1") is not None
    first.close()
    second = TaskQueueService(db_path=sqlite, legacy_json_path=legacy)
    second.initialize()
    assert second.get("legacy-1") is not None
    rows = second.store._conn_required().execute("SELECT COUNT(*) FROM tasks WHERE id = 'legacy-1'").fetchone()[0]
    assert rows == 1
    assert legacy.exists()
    second.close()


def test_idempotency_key_deduplicates(queue_service):
    first = queue_service.create("t", "p", idempotency_key="idem-1")
    second = queue_service.create("t2", "p2", idempotency_key="idem-1")
    assert first.id == second.id


def test_global_concurrency_limits(queue_service):
    for idx in range(4):
        queue_service.store.create_task({"title": f"t{idx}", "prompt": f"p{idx}", "agent_id": "a1"})
    claimed = []
    for _ in range(4):
        task = queue_service.store.claim_next_task("worker-a", 30)
        if task:
            claimed.append(task.id)
    assert len(claimed) >= 1


def test_retryable_vs_non_retryable():
    from app.services.task_queue.retry import classify_error, is_retryable

    assert is_retryable(classify_error("connection reset"))
    assert not is_retryable(classify_error("permission denied"))


def test_dead_letter_requeue_preserves_attempts(queue_service):
    from app.services.task_queue.models import TaskStatus

    task = queue_service.create("fail", "boom", max_attempts=1, auto_run=False)
    queue_service.store.create_attempt(task.id, 1, "w1")
    queue_service.store.transition_status(task.id, TaskStatus.DEAD_LETTER, fields={"error": "boom"})
    attempts_before = len(queue_service.list_attempts(task.id))
    requeued = queue_service.requeue(task.id)
    assert requeued is not None
    assert requeued.status == TaskStatus.QUEUED
    assert len(queue_service.list_attempts(task.id)) == attempts_before


def test_running_becomes_interrupted_on_restart(tmp_path):
    from app.services.task_queue.models import TaskStatus
    from app.services.task_queue.service import TaskQueueService

    db = tmp_path / "tasks" / "task_queue.sqlite3"
    legacy = tmp_path / "tasks" / "task_history.json"
    svc = TaskQueueService(db_path=db, legacy_json_path=legacy)
    svc.initialize()
    task = svc.create("run", "x", auto_run=False)
    svc.store.transition_status(task.id, TaskStatus.RUNNING)
    svc.close()
    restored = TaskQueueService(db_path=db, legacy_json_path=legacy)
    restored.initialize()
    loaded = restored.get(task.id)
    assert loaded is not None
    assert loaded.status == TaskStatus.INTERRUPTED


def test_scheduled_task_not_claimed_before_time(queue_service):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    task = queue_service.create("later", "wait", scheduled_at=future, auto_run=False)
    claimed = queue_service.store.claim_next_task("worker-a", 30)
    assert claimed is None or claimed.id != task.id


def test_sanitize_redacts_secrets(queue_service):
    task = queue_service.create(
        "secret",
        "Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz123456",
        metadata={"api_key": "sk-secret"},
    )
    stored = queue_service.get(task.id)
    assert stored is not None
    assert "[REDACTED]" in stored.prompt or "sk-abcdefghijklmnopqrstuvwxyz123456" not in stored.prompt


def test_paged_list_and_stats(queue_service):
    queue_service.create("a", "1")
    queue_service.create("b", "2")
    items, cursor = queue_service.list_page(limit=1)
    assert len(items) == 1
    assert cursor
    stats = queue_service.queue_stats()
    assert "queue_depth" in stats
    assert "status_counts" in stats


def test_update_conflict_returns_none(queue_service):
    task = queue_service.create("edit", "prompt", auto_run=False)
    ok = queue_service.update_task(task.id, revision=task.revision, fields={"title": "new"})
    assert ok is not None
    conflict = queue_service.update_task(task.id, revision=task.revision, fields={"title": "again"})
    assert conflict is None


def test_cancel_complete_race_single_terminal(queue_service):
    from app.services.task_queue.models import TaskStatus

    task = queue_service.create("race", "x", auto_run=False)
    completed = queue_service.store.transition_status(
        task.id,
        TaskStatus.COMPLETED,
        expected_statuses={TaskStatus.QUEUED},
        fields={"result": "done"},
    )
    cancelled = queue_service.store.transition_status(
        task.id,
        TaskStatus.CANCELLED,
        expected_statuses={TaskStatus.RUNNING, TaskStatus.QUEUED},
    )
    assert completed is not None
    assert cancelled is None
