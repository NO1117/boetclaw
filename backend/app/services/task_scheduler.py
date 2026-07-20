"""Task scheduling and management."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TASK_TRANSITIONS = {
    TaskStatus.PENDING: {
        TaskStatus.RUNNING,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    },
    TaskStatus.CANCELLING: {TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: {TaskStatus.PENDING},
    TaskStatus.FAILED: {TaskStatus.PENDING},
    TaskStatus.CANCELLED: {TaskStatus.PENDING},
}


@dataclass
class Task:
    id: str
    title: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    thread_id: str = ""
    trace_id: str = ""
    run_id: str = ""
    result: str = ""
    error: str = ""
    gateway: str = ""
    gateway_user: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "status": self.status.value,
            "thread_id": self.thread_id,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "result": self.result,
            "error": self.error,
            "gateway": self.gateway,
            "gateway_user": self.gateway_user,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        status = TaskStatus(data.get("status", TaskStatus.PENDING.value))
        error = str(data.get("error", ""))
        updated_at = str(data.get("updated_at") or datetime.now(timezone.utc).isoformat())
        if status in {TaskStatus.RUNNING, TaskStatus.CANCELLING}:
            status = TaskStatus.FAILED
            error = error or "Task interrupted by service restart"
            updated_at = datetime.now(timezone.utc).isoformat()
        return cls(
            id=str(data.get("id", uuid.uuid4().hex[:12])),
            title=str(data.get("title", "")),
            prompt=str(data.get("prompt", "")),
            status=status,
            thread_id=str(data.get("thread_id", "")),
            trace_id=str(data.get("trace_id", "")),
            run_id=str(data.get("run_id", "")),
            result=str(data.get("result", "")),
            error=error,
            gateway=str(data.get("gateway", "")),
            gateway_user=str(data.get("gateway_user", "")),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=updated_at,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )


class TaskScheduler:
    """Simple task scheduler with JSON persistence."""

    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = store_path or (settings.workspace_dir / "tasks" / "task_history.json")
        self._tasks: dict[str, Task] = {}
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            rows = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                task = Task.from_dict(row)
            except ValueError:
                continue
            if task.id:
                self._tasks[task.id] = task
        self._save()

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [task.to_dict() for task in self.list_tasks()]
        self.store_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(
        self,
        title: str,
        prompt: str,
        *,
        gateway: str = "",
        gateway_user: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        task = Task(
            id=uuid.uuid4().hex[:12],
            title=title,
            prompt=prompt,
            thread_id=uuid.uuid4().hex[:16],
            gateway=gateway,
            gateway_user=gateway_user,
            metadata=metadata or {},
        )
        self._tasks[task.id] = task
        self._save()
        emit_event(EventType.TODO_UPDATE, {"action": "create", "task_id": task.id, "title": title})
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

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
    ) -> Task | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        if expected is not None and task.status not in expected:
            return None
        if task.status != status and status not in _TASK_TRANSITIONS.get(task.status, set()):
            return None
        previous = task.status
        task.status = status
        task.updated_at = datetime.now(timezone.utc).isoformat()
        if result:
            task.result = result
        if error:
            task.error = error
        if trace_id:
            task.trace_id = trace_id
        if run_id:
            task.run_id = run_id
        self._save()
        if previous != status:
            emit_event(
                EventType.RUN_STATUS,
                {
                    "task_id": task.id,
                    "thread_id": task.thread_id,
                    "agent_id": str(task.metadata.get("agent_id", "default")),
                    "previous_status": previous.value,
                    "status": status.value,
                },
                trace_id=task.trace_id or None,
                run_id=task.run_id or None,
            )
        return task


task_scheduler = TaskScheduler()
