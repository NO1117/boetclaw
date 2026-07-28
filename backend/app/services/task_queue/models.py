"""Task queue domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    LEASED = "leased"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"
    INTERRUPTED = "interrupted"

    # Legacy alias
    PENDING = "queued"

    @classmethod
    def from_legacy(cls, value: str) -> "TaskStatus":
        if value == "pending":
            return cls.QUEUED
        return cls(value)

    def to_legacy(self) -> str:
        if self == TaskStatus.QUEUED:
            return "pending"
        return self.value


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.DEAD_LETTER,
    TaskStatus.INTERRUPTED,
}

ACTIVE_STATUSES = {
    TaskStatus.LEASED,
    TaskStatus.RUNNING,
    TaskStatus.CANCELLING,
}

_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {
        TaskStatus.SCHEDULED,
        TaskStatus.LEASED,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.SCHEDULED: {
        TaskStatus.QUEUED,
        TaskStatus.LEASED,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.LEASED: {
        TaskStatus.RUNNING,
        TaskStatus.QUEUED,
        TaskStatus.RETRY_WAIT,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.RETRY_WAIT,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
        TaskStatus.DEAD_LETTER,
    },
    TaskStatus.RETRY_WAIT: {
        TaskStatus.QUEUED,
        TaskStatus.LEASED,
        TaskStatus.CANCELLING,
        TaskStatus.CANCELLED,
        TaskStatus.DEAD_LETTER,
    },
    TaskStatus.CANCELLING: {TaskStatus.CANCELLED, TaskStatus.INTERRUPTED},
    TaskStatus.COMPLETED: {TaskStatus.QUEUED},
    TaskStatus.FAILED: {TaskStatus.QUEUED, TaskStatus.DEAD_LETTER},
    TaskStatus.CANCELLED: {TaskStatus.QUEUED},
    TaskStatus.DEAD_LETTER: {TaskStatus.QUEUED},
    TaskStatus.INTERRUPTED: {TaskStatus.QUEUED},
}


class BackoffStrategy(str, Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class ErrorCategory(str, Enum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    CONFIG = "config"
    PERMISSION = "permission"
    VALIDATION = "validation"
    SECURITY = "security"
    UNKNOWN = "unknown"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class TaskAttempt:
    id: int
    task_id: str
    attempt_number: int
    status: str
    worker_id: str = ""
    run_id: str = ""
    trace_id: str = ""
    thread_id: str = ""
    result_summary: str = ""
    error_summary: str = ""
    error_category: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "attempt_number": self.attempt_number,
            "status": self.status,
            "worker_id": self.worker_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
            "result_summary": self.result_summary,
            "error_summary": self.error_summary,
            "error_category": self.error_category,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TaskRecord:
    id: str
    title: str
    prompt: str
    status: TaskStatus
    agent_id: str = "default"
    priority: int = 0
    scheduled_at: str = ""
    max_attempts: int = 3
    attempt_count: int = 0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_base_seconds: int = 5
    backoff_max_seconds: int = 300
    timeout_seconds: int = 600
    idempotency_key: str = ""
    thread_id: str = ""
    trace_id: str = ""
    run_id: str = ""
    result: str = ""
    error: str = ""
    gateway: str = ""
    gateway_user: str = ""
    source: str = "api"
    revision: int = 1
    retry_after: str = ""
    run_snapshot_json: str = "{}"
    metadata_json: str = "{}"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    lease_owner: str = ""
    lease_expires_at: str = ""
    migrated_from_json: int = 0

    @property
    def metadata(self) -> dict[str, Any]:
        import json

        try:
            data = json.loads(self.metadata_json or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def run_snapshot(self) -> dict[str, Any]:
        import json

        try:
            data = json.loads(self.run_snapshot_json or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def to_legacy_dict(self) -> dict[str, Any]:
        meta = dict(self.metadata)
        if self.agent_id:
            meta.setdefault("agent_id", self.agent_id)
        return {
            "id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "status": self.status.to_legacy(),
            "thread_id": self.thread_id,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "result": self.result,
            "error": self.error,
            "gateway": self.gateway,
            "gateway_user": self.gateway_user,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": meta,
        }

    def to_dict(self) -> dict[str, Any]:
        data = self.to_legacy_dict()
        data.update(
            {
                "status": self.status.value,
                "agent_id": self.agent_id,
                "priority": self.priority,
                "scheduled_at": self.scheduled_at,
                "max_attempts": self.max_attempts,
                "attempt_count": self.attempt_count,
                "backoff_strategy": self.backoff_strategy.value,
                "backoff_base_seconds": self.backoff_base_seconds,
                "backoff_max_seconds": self.backoff_max_seconds,
                "timeout_seconds": self.timeout_seconds,
                "idempotency_key": self.idempotency_key,
                "source": self.source,
                "revision": self.revision,
                "retry_after": self.retry_after,
                "run_snapshot": self.run_snapshot,
                "lease_owner": self.lease_owner,
                "lease_expires_at": self.lease_expires_at,
            }
        )
        return data


@dataclass
class TaskEvent:
    id: int
    task_id: str
    event_type: str
    payload_json: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        import json

        try:
            payload = json.loads(self.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        return {
            "id": self.id,
            "task_id": self.task_id,
            "event_type": self.event_type,
            "payload": payload,
            "created_at": self.created_at,
        }


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    if current == target:
        return True
    return target in _TRANSITIONS.get(current, set())
