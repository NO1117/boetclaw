"""High-level durable task queue service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event
from app.services.task_queue.models import TaskRecord, TaskStatus
from app.services.task_queue.sanitizer import sanitize_metadata, sanitize_snapshot, sanitize_text
from app.services.task_queue.store import TaskQueueStore
from app.services.task_queue.worker import TaskQueueWorker


class TaskQueueService:
    def __init__(
        self,
        db_path: Path | None = None,
        legacy_json_path: Path | None = None,
    ) -> None:
        self.store = TaskQueueStore(db_path=db_path, legacy_json_path=legacy_json_path)
        self.worker = TaskQueueWorker(self.store)
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self.store.initialize()
        self._initialized = True

    def close(self) -> None:
        import asyncio

        if self.worker.running:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.worker.stop())
                else:
                    loop.run_until_complete(self.worker.stop())
            except RuntimeError:
                pass
        self.store.close()
        self._initialized = False

    async def start_worker(self) -> None:
        self.initialize()
        self.worker.start()

    async def stop_worker(self) -> None:
        await self.worker.stop()

    def create(
        self,
        title: str,
        prompt: str,
        *,
        gateway: str = "",
        gateway_user: str = "",
        metadata: dict[str, Any] | None = None,
        auto_run: bool = True,
        agent_id: str = "",
        scheduled_at: str = "",
        priority: int = 0,
        max_attempts: int | None = None,
        idempotency_key: str = "",
        run_snapshot: dict[str, Any] | None = None,
        source: str = "api",
    ) -> TaskRecord:
        self.initialize()
        payload = {
            "title": title,
            "prompt": prompt,
            "gateway": gateway,
            "gateway_user": gateway_user,
            "metadata": metadata or {},
            "agent_id": agent_id or str((metadata or {}).get("agent_id") or settings.default_agent_id),
            "scheduled_at": scheduled_at,
            "priority": priority,
            "max_attempts": max_attempts or settings.task_queue_default_max_attempts,
            "idempotency_key": idempotency_key,
            "run_snapshot": run_snapshot or {},
            "source": source,
        }
        task = self.store.create_task(payload)
        emit_event(
            EventType.TODO_UPDATE,
            {"action": "create", "task_id": task.id, "title": title},
        )
        if auto_run and not scheduled_at:
            # worker will pick up queued tasks
            pass
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        self.initialize()
        return self.store.get_task(task_id)

    def list_tasks(self, status: TaskStatus | str | None = None) -> list[TaskRecord]:
        self.initialize()
        status_value = None
        if status is not None:
            if isinstance(status, TaskStatus):
                status_value = status.value
            else:
                status_value = TaskStatus.from_legacy(str(status)).value
        tasks, _ = self.store.list_tasks(status=status_value, limit=500)
        return tasks

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        expected: set[TaskStatus] | None = None,
        result: str = "",
        error: str = "",
        trace_id: str = "",
        run_id: str = "",
    ) -> TaskRecord | None:
        self.initialize()
        fields: dict[str, Any] = {"lease_owner": "", "lease_expires_at": ""}
        if result:
            fields["result"] = sanitize_text(result)
        if error:
            fields["error"] = sanitize_text(error)
        if trace_id:
            fields["trace_id"] = trace_id
        if run_id:
            fields["run_id"] = run_id
        previous = self.store.get_task(task_id)
        updated = self.store.transition_status(
            task_id,
            status,
            expected_statuses=expected,
            fields=fields,
        )
        if updated and previous and previous.status != status:
            emit_event(
                EventType.RUN_STATUS,
                {
                    "task_id": task_id,
                    "thread_id": updated.thread_id,
                    "agent_id": updated.agent_id,
                    "previous_status": previous.status.to_legacy(),
                    "status": status.to_legacy(),
                },
                trace_id=updated.trace_id or None,
                run_id=updated.run_id or None,
            )
        return updated

    def queue_stats(self) -> dict[str, Any]:
        self.initialize()
        return self.store.metrics_snapshot()

    def pause(self) -> bool:
        self.initialize()
        return self.store.set_paused(True)

    def resume(self) -> bool:
        self.initialize()
        return self.store.set_paused(False)

    def requeue(self, task_id: str) -> TaskRecord | None:
        self.initialize()
        return self.store.transition_status(
            task_id,
            TaskStatus.QUEUED,
            expected_statuses={TaskStatus.DEAD_LETTER, TaskStatus.FAILED, TaskStatus.INTERRUPTED},
            fields={"retry_after": "", "error": "", "result": ""},
        )

    def cancel(self, task_id: str) -> TaskRecord | None:
        self.initialize()
        task = self.store.get_task(task_id)
        if not task:
            return None
        if task.status == TaskStatus.CANCELLED:
            return task
        if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.DEAD_LETTER}:
            return None
        if task.status in {TaskStatus.RUNNING, TaskStatus.LEASED}:
            self.store.transition_status(
                task_id,
                TaskStatus.CANCELLING,
                expected_statuses={TaskStatus.RUNNING, TaskStatus.LEASED, TaskStatus.QUEUED, TaskStatus.SCHEDULED},
            )
            return self.store.transition_status(
                task_id,
                TaskStatus.CANCELLED,
                expected_statuses={TaskStatus.CANCELLING, TaskStatus.RUNNING, TaskStatus.LEASED, TaskStatus.QUEUED},
            )
        return self.store.transition_status(
            task_id,
            TaskStatus.CANCELLED,
            expected_statuses={TaskStatus.QUEUED, TaskStatus.SCHEDULED, TaskStatus.RETRY_WAIT},
        )

    def list_page(self, **filters: Any) -> tuple[list[TaskRecord], str | None]:
        self.initialize()
        return self.store.list_tasks(**filters)

    def list_attempts(self, task_id: str):
        self.initialize()
        return self.store.list_attempts(task_id)

    def list_events(self, task_id: str | None = None, after_id: int = 0, limit: int = 200):
        self.initialize()
        if task_id:
            return self.store.list_events(task_id, after_id=after_id, limit=limit)
        return self.store.list_all_events(after_id=after_id, limit=limit)

    def update_task(self, task_id: str, *, revision: int, fields: dict[str, Any]) -> TaskRecord | None:
        self.initialize()
        updates = dict(fields)
        if "metadata" in updates and isinstance(updates["metadata"], dict):
            updates["metadata_json"] = sanitize_metadata(updates.pop("metadata"))
        if "prompt" in updates:
            updates["prompt"] = sanitize_text(str(updates["prompt"]))
        if "title" in updates:
            updates["title"] = sanitize_text(str(updates["title"]))
        if "scheduled_at" in updates and updates["scheduled_at"]:
            # moving scheduled time keeps scheduled status
            pass
        return self.store.update_task_fields(task_id, revision=revision, fields=updates)

    def capture_run_snapshot(self, agent_id: str) -> dict[str, Any]:
        try:
            from app.agents.profile.service import agent_profile_service

            effective = agent_profile_service.get_effective(agent_id)
            snapshot = effective.model_dump()
            snapshot["connection_id"] = str(snapshot.get("connection_id") or "")
            return sanitize_snapshot(snapshot)
        except Exception:  # noqa: BLE001
            return sanitize_snapshot({"agent_id": agent_id})


def _default_paths() -> tuple[Path, Path]:
    base = settings.workspace_dir / "tasks"
    return base / "task_queue.sqlite3", base / "task_history.json"


_db, _legacy = _default_paths()
task_queue_service = TaskQueueService(db_path=_db, legacy_json_path=_legacy)
