"""Observability and monitoring routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.schemas import TraceEventResponse
from app.core.observability import EventType, trace_store
from app.core.timeline import build_timeline
from app.security.approval import approval_service
from app.services.gateway.manager import channel_manager
from app.services.task_scheduler import TaskStatus, task_scheduler
from app.tools.mcp_manager import mcp_manager

router = APIRouter(prefix="/monitor", tags=["Monitor"])


def _escape_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _metric_line(name: str, value: int | float, labels: dict[str, str] | None = None) -> str:
    if not labels:
        return f"{name} {value}"
    encoded = ",".join(f'{key}="{_escape_label(val)}"' for key, val in labels.items())
    return f"{name}{{{encoded}}} {value}"


def _count_by_label(events, event_type: EventType, label_key: str, default: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if event.event_type != event_type:
            continue
        label = str(event.data.get(label_key) or default)
        counts[label] = counts.get(label, 0) + 1
    return counts


def _tool_call_counts(events) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    statuses = {
        EventType.TOOL_CALL: "started",
        EventType.TOOL_RESULT: "completed",
    }
    for event in events:
        status = statuses.get(event.event_type)
        if status is None:
            continue
        tool = str(event.data.get("tool") or "unknown")
        key = (tool, status)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _agent_run_durations_seconds(events) -> list[float]:
    starts: dict[str, datetime] = {}
    durations: list[float] = []
    for event in events:
        if event.event_type not in (EventType.AGENT_START, EventType.AGENT_END):
            continue
        try:
            timestamp = datetime.fromisoformat(event.timestamp)
        except ValueError:
            continue
        if event.event_type == EventType.AGENT_START:
            starts[event.run_id] = timestamp
        elif event.run_id in starts:
            duration = (timestamp - starts[event.run_id]).total_seconds()
            if duration >= 0:
                durations.append(duration)
    return durations


def _histogram_lines(name: str, values: list[float], buckets: list[float]) -> list[str]:
    lines: list[str] = []
    for bucket in buckets:
        count = sum(1 for value in values if value <= bucket)
        lines.append(_metric_line(f"{name}_bucket", count, {"le": str(bucket)}))
    lines.append(_metric_line(f"{name}_bucket", len(values), {"le": "+Inf"}))
    lines.append(_metric_line(f"{name}_count", len(values)))
    lines.append(_metric_line(f"{name}_sum", round(sum(values), 6)))
    return lines


@router.get("/health")
async def health(request: Request):
    from app.core.agent import agent_manager
    from app.core.checkpoint import checkpoint_provider

    app_ready = getattr(request.app.state, "agent_ready", None)
    agent_ready = app_ready if app_ready is not None else (agent_manager._agent is not None)
    checkpoint = checkpoint_provider.status()
    from app.memory.service import memory_service

    memory = memory_service.health()
    status = "degraded" if checkpoint["status"] == "error" or memory.get("status") == "error" else "healthy"
    return {
        "status": status,
        "ready": getattr(request.app.state, "ready", True),
        "agent_ready": agent_ready,
        "checkpoint": checkpoint,
        "memory": memory,
    }


@router.get("/stats")
async def stats():
    tasks = task_scheduler.list_tasks()
    status_counts = {s.value: 0 for s in TaskStatus}
    for t in tasks:
        status_counts[t.status.value] += 1

    return {
        "tasks": status_counts,
        "trace_events": len(trace_store._events),
        "event_types": {e.value: sum(1 for ev in trace_store._events if ev.event_type == e) for e in EventType},
    }


@router.get("/metrics")
async def metrics():
    tasks = task_scheduler.list_tasks()
    status_counts = {s.value: 0 for s in TaskStatus}
    for task in tasks:
        status_counts[task.status.value] += 1
    events = trace_store._events
    agent_run_counts = {
        "started": sum(1 for ev in events if ev.event_type == EventType.AGENT_START),
        "completed": sum(1 for ev in events if ev.event_type == EventType.AGENT_END),
        "failed": sum(1 for ev in events if ev.event_type == EventType.ERROR),
    }
    tool_call_counts = _tool_call_counts(events)
    guard_block_counts = _count_by_label(events, EventType.GUARD_BLOCK, "guardian", "tool_guard")
    provider_retry_counts = _count_by_label(events, EventType.PROVIDER_RETRY, "provider", "unknown")
    agent_run_durations = _agent_run_durations_seconds(events)

    lines = [
        "# HELP boetclaw_agent_runs_total Number of agent run events by status.",
        "# TYPE boetclaw_agent_runs_total counter",
        *[
            _metric_line("boetclaw_agent_runs_total", count, {"status": status})
            for status, count in agent_run_counts.items()
        ],
        "# HELP boetclaw_agent_run_duration_seconds Agent run duration in seconds.",
        "# TYPE boetclaw_agent_run_duration_seconds histogram",
        *_histogram_lines("boetclaw_agent_run_duration_seconds", agent_run_durations, [1, 5, 10, 30, 60, 300]),
        "# HELP boetclaw_tool_calls_total Number of tool call events by tool and status.",
        "# TYPE boetclaw_tool_calls_total counter",
        *[
            _metric_line("boetclaw_tool_calls_total", count, {"tool": tool, "status": status})
            for (tool, status), count in sorted(tool_call_counts.items())
        ],
        "# HELP boetclaw_guard_blocks_total Number of guard blocks by guardian.",
        "# TYPE boetclaw_guard_blocks_total counter",
        *[
            _metric_line("boetclaw_guard_blocks_total", count, {"guardian": guardian})
            for guardian, count in sorted(guard_block_counts.items())
        ],
        "# HELP boetclaw_llm_retries_total Number of provider retry/resolve events by provider.",
        "# TYPE boetclaw_llm_retries_total counter",
        *[
            _metric_line("boetclaw_llm_retries_total", count, {"provider": provider})
            for provider, count in sorted(provider_retry_counts.items())
        ],
        "# HELP boetclaw_tasks_total Number of tasks by status.",
        "# TYPE boetclaw_tasks_total gauge",
        *[_metric_line("boetclaw_tasks_total", count, {"status": status}) for status, count in status_counts.items()],
        "# HELP boetclaw_trace_events_total Number of trace events in memory.",
        "# TYPE boetclaw_trace_events_total gauge",
        _metric_line("boetclaw_trace_events_total", len(events)),
        "# HELP boetclaw_trace_events_by_type Number of trace events by type.",
        "# TYPE boetclaw_trace_events_by_type gauge",
        *[
            _metric_line(
                "boetclaw_trace_events_by_type",
                sum(1 for ev in events if ev.event_type == event_type),
                {"event_type": event_type.value},
            )
            for event_type in EventType
        ],
        "# HELP boetclaw_approvals_pending Number of pending tool approvals.",
        "# TYPE boetclaw_approvals_pending gauge",
        _metric_line("boetclaw_approvals_pending", len(approval_service.list_pending())),
        "# HELP boetclaw_gateway_queue_depth Gateway queue depth by platform.",
        "# TYPE boetclaw_gateway_queue_depth gauge",
        *[
            _metric_line("boetclaw_gateway_queue_depth", item["queue_depth"], {"platform": item["name"]})
            for item in channel_manager.status()
        ],
        "# HELP boetclaw_mcp_recover_total Number of MCP reload/recover attempts by result.",
        "# TYPE boetclaw_mcp_recover_total counter",
        *[
            _metric_line("boetclaw_mcp_recover_total", count, {"result": result})
            for result, count in mcp_manager.recover_counts().items()
        ],
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@router.get("/events", response_model=list[TraceEventResponse])
async def recent_events(limit: int = 100):
    events = trace_store._events[-limit:]
    return [TraceEventResponse(**e.to_dict()) for e in reversed(events)]


@router.get("/trace/{trace_id}/timeline")
async def trace_timeline(trace_id: str):
    timeline = build_timeline(trace_id)
    if timeline["event_count"] == 0:
        raise HTTPException(status_code=404, detail="trace not found")
    return timeline
