"""Phase 24 tests: task scheduler JSON persistence."""


def test_task_scheduler_persists_create_and_update(tmp_path):
    from app.services.task_scheduler import TaskScheduler, TaskStatus

    store_path = tmp_path / "tasks" / "task_history.json"
    svc = TaskScheduler(store_path=store_path)
    task = svc.create("日报", "生成日报", metadata={"agent_id": "a1", "well_id": "w1"})
    svc.update_status(task.id, TaskStatus.COMPLETED, result="ok", trace_id="trace-1", run_id="run-1")

    restored = TaskScheduler(store_path=store_path)
    loaded = restored.get(task.id)

    assert loaded is not None
    assert loaded.status == TaskStatus.COMPLETED
    assert loaded.result == "ok"
    assert loaded.trace_id == "trace-1"
    assert loaded.metadata["well_id"] == "w1"


def test_task_scheduler_recovers_running_as_failed(tmp_path):
    from app.services.task_scheduler import TaskScheduler, TaskStatus

    store_path = tmp_path / "tasks" / "task_history.json"
    svc = TaskScheduler(store_path=store_path)
    task = svc.create("运行中任务", "ping")
    svc.update_status(task.id, TaskStatus.RUNNING)

    restored = TaskScheduler(store_path=store_path)
    loaded = restored.get(task.id)

    assert loaded is not None
    assert loaded.status == TaskStatus.FAILED
    assert "restart" in loaded.error.lower()
