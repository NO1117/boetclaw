"""Logging, tracing and execution event tracking."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

from app.core.config import settings

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
run_id_var: ContextVar[str] = ContextVar("run_id", default="")


class EventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    RUN_STATUS = "run_status"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_END = "subagent_end"
    TODO_UPDATE = "todo_update"
    ERROR = "error"
    GATEWAY_MESSAGE = "gateway_message"
    PLAN_CREATED = "plan_created"
    PLAN_CONFIRMED = "plan_confirmed"
    GUARD_BLOCK = "guard_block"
    GUARD_APPROVED = "guard_approved"
    APPROVAL_REQUESTED = "approval_requested"
    SKILL_LOADED = "skill_loaded"
    CRON_TRIGGER = "cron_trigger"
    HEARTBEAT = "heartbeat"
    MCP_RECOVER = "mcp_recover"
    PROVIDER_RETRY = "provider_retry"
    MEMORY_PERSIST = "memory_persist"
    MEMORY_SKIP = "memory_skip"


@dataclass
class TraceEvent:
    id: str
    trace_id: str
    run_id: str
    event_type: EventType
    timestamp: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "event_type": self.event_type.value,
        }


class TraceStore:
    """In-memory trace store with optional JSONL persistence."""

    def __init__(
        self,
        max_events: int = 10000,
        persist_path: Path | None = None,
        persist_enabled: bool | None = None,
    ) -> None:
        self._events: list[TraceEvent] = []
        self._max_events = max_events
        self._subscribers: dict[str, list] = {}
        self._lock = threading.Lock()
        self._persist_enabled = persist_enabled if persist_enabled is not None else settings.trace_persist_enabled
        self._persist_path = persist_path or (settings.workspace_dir / ".cache" / "traces.jsonl")
        if self._persist_enabled:
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            lines = self._persist_path.read_text(encoding="utf-8").splitlines()
            max_lines = settings.trace_persist_max_lines
            for line in lines[-max_lines:]:
                if not line.strip():
                    continue
                raw = json.loads(line)
                et = EventType(raw["event_type"])
                self._events.append(
                    TraceEvent(
                        id=raw["id"],
                        trace_id=raw["trace_id"],
                        run_id=raw["run_id"],
                        event_type=et,
                        timestamp=raw["timestamp"],
                        data=raw.get("data", {}),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            get_logger("trace_store").warning("trace_load_failed", error=str(exc))

    def _append_to_disk(self, event: TraceEvent) -> None:
        if not self._persist_enabled:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            get_logger("trace_store").warning("trace_persist_failed", error=str(exc))

    def add(self, event: TraceEvent) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events :]
            self._append_to_disk(event)
        for subs in self._subscribers.values():
            for queue in subs:
                queue.append(event)

    def get_by_trace(self, trace_id: str) -> list[TraceEvent]:
        return [e for e in self._events if e.trace_id == trace_id]

    def get_by_run(self, run_id: str) -> list[TraceEvent]:
        return [e for e in self._events if e.run_id == run_id]

    def subscribe(self, run_id: str) -> list:
        queue: list = []
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: list) -> None:
        subs = self._subscribers.get(run_id, [])
        if queue in subs:
            subs.remove(queue)


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


def get_logger(name: str = "boetclaw"):
    return structlog.get_logger(name)


# Instantiated after get_logger so disk-load warnings do not NameError at import time.
trace_store = TraceStore()


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def new_run_id() -> str:
    return uuid.uuid4().hex


def emit_event(
    event_type: EventType,
    data: dict[str, Any] | None = None,
    *,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> TraceEvent:
    event = TraceEvent(
        id=uuid.uuid4().hex[:12],
        trace_id=trace_id or trace_id_var.get() or new_trace_id(),
        run_id=run_id or run_id_var.get() or new_run_id(),
        event_type=event_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        data=data or {},
    )
    trace_store.add(event)
    get_logger().info(
        event_type.value,
        trace_id=event.trace_id,
        run_id=event.run_id,
        **(data or {}),
    )
    return event


class TraceSpan:
    """Simple span context manager for timing operations."""

    def __init__(self, name: str, **metadata: Any) -> None:
        self.name = name
        self.metadata = metadata
        self.start = 0.0

    def __enter__(self) -> TraceSpan:
        self.start = time.perf_counter()
        emit_event(EventType.THINKING, {"span": self.name, "status": "start", **self.metadata})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = (time.perf_counter() - self.start) * 1000
        if exc:
            emit_event(
                EventType.ERROR,
                {"span": self.name, "error": str(exc), "duration_ms": duration_ms},
            )
        else:
            emit_event(
                EventType.THINKING,
                {"span": self.name, "status": "end", "duration_ms": duration_ms},
            )


def serialize_for_sse(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
