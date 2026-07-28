"""Task scheduling facade with durable SQLite queue backend."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.task_queue.models import TaskRecord, TaskStatus as QueueStatus
from app.services.task_queue.service import TaskQueueService


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    LEASED = "leased"
    RETRY_WAIT = "retry_wait"
    DEAD_LETTER = "dead_letter"
    INTERRUPTED = "interrupted"

    @classmethod
    def from_queue(cls, status: QueueStatus | str) -> "TaskStatus":
        value = status.value if isinstance(status, QueueStatus) else str(status)
        if value == "queued":
            return cls.PENDING
        try:
            return cls(value)
        except ValueError:
            return cls.PENDING

    def to_queue(self) -> QueueStatus:
        if self == TaskStatus.PENDING:
            return QueueStatus.QUEUED
        return QueueStatus(self.value)


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
    revision: int = 1
    scheduled_at: str = ""
    priority: int = 0
    attempt_count: int = 0
    max_attempts: int = 3
    retry_after: str = ""
    agent_id: str = "default"
    source: str = "api"
    run_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "status": self.status.value if self.status != TaskStatus.PENDING else "pending",
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
            "revision": self.revision,
            "scheduled_at": self.scheduled_at,
            "priority": self.priority,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "retry_after": self.retry_after,
            "agent_id": self.agent_id,
            "source": self.source,
            "run_snapshot": self.run_snapshot,
        }

    @classmethod
    def from_record(cls, record: TaskRecord) -> "Task":
        return cls(
            id=record.id,
            title=record.title,
            prompt=record.prompt,
            status=TaskStatus.from_queue(record.status),
            thread_id=record.thread_id,
            trace_id=record.trace_id,
            run_id=record.run_id,
            result=record.result,
            error=record.error,
            gateway=record.gateway,
            gateway_user=record.gateway_user,
            created_at=record.created_at,
            updated_at=record.updated_at,
            metadata=record.metadata,
            revision=record.revision,
            scheduled_at=record.scheduled_at,
            priority=record.priority,
            attempt_count=record.attempt_count,
            max_attempts=record.max_attempts,
            retry_after=record.retry_after,
            agent_id=record.agent_id,
            source=record.source,
            run_snapshot=record.run_snapshot,
        )


class TaskScheduler:
    """Compatibility scheduler backed by durable SQLite queue."""

    def __init__(self, store_path: Path | None = None, db_path: Path | None = None) -> None:
        legacy = store_path or (settings.workspace_dir / "tasks" / "task_history.json")
        sqlite_path = db_path or legacy.parent / "task_queue.sqlite3"
        self.store_path = legacy
        self._service = TaskQueueService(db_path=sqlite_path, legacy_json_path=legacy)
        self._service.initialize()

    @property
    def service(self) -> TaskQueueService:
        return self._service

    def _load(self) -> None:
        self._service.initialize()

    def _save(self) -> None:
        return

    def create(
        self,
        title: str,
        prompt: str,
        *,
        gateway: str = "",
        gateway_user: str = "",
        metadata: dict[str, Any] | None = None,
        auto_run: bool = True,
        scheduled_at: str = "",
        priority: int = 0,
        max_attempts: int | None = None,
        idempotency_key: str = "",
        agent_id: str = "",
        source: str = "api",
    ) -> Task:
        meta = metadata or {}
        resolved_agent = agent_id or str(meta.get("agent_id") or settings.default_agent_id)
        snapshot = self._service.capture_run_snapshot(resolved_agent)
        record = self._service.create(
            title,
            prompt,
            gateway=gateway,
            gateway_user=gateway_user,
            metadata=meta,
            auto_run=auto_run,
            agent_id=resolved_agent,
            scheduled_at=scheduled_at,
            priority=priority,
            max_attempts=max_attempts,
            idempotency_key=idempotency_key,
            run_snapshot=snapshot,
            source=source,
        )
        return Task.from_record(record)

    def get(self, task_id: str) -> Task | None:
        record = self._service.get(task_id)
        return Task.from_record(record) if record else None

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        queue_status = status.to_queue().value if status else None
        if status == TaskStatus.PENDING:
            queue_status = QueueStatus.QUEUED.value
        records = self._service.list_tasks(queue_status)
        return [Task.from_record(record) for record in records]

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
        expected_queue = {item.to_queue() for item in expected} if expected else None
        record = self._service.update_status(
            task_id,
            status.to_queue(),
            expected=expected_queue,
            result=result,
            error=error,
            trace_id=trace_id,
            run_id=run_id,
        )
        return Task.from_record(record) if record else None


task_scheduler = TaskScheduler()
