"""Structured trace timeline builder."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.observability import EventType, TraceEvent, trace_store

_CATEGORY_MAP: dict[EventType, str] = {
    EventType.PLAN_CREATED: "plan",
    EventType.PLAN_CONFIRMED: "plan",
    EventType.GUARD_BLOCK: "guard",
    EventType.GUARD_APPROVED: "guard",
    EventType.APPROVAL_REQUESTED: "guard",
    EventType.SUBAGENT_START: "subagent",
    EventType.SUBAGENT_END: "subagent",
    EventType.TOOL_CALL: "tool",
    EventType.TOOL_RESULT: "tool",
    EventType.THINKING: "thinking",
    EventType.AGENT_START: "agent",
    EventType.AGENT_END: "agent",
    EventType.TODO_UPDATE: "plan",
    EventType.ERROR: "error",
    EventType.GATEWAY_MESSAGE: "gateway",
    EventType.CRON_TRIGGER: "scheduler",
    EventType.HEARTBEAT: "scheduler",
    EventType.SKILL_LOADED: "skill",
    EventType.MEMORY_PERSIST: "memory",
    EventType.MEMORY_SKIP: "memory",
    EventType.MEMORY_CREATED: "memory",
    EventType.MEMORY_CANDIDATE: "memory",
    EventType.MEMORY_APPROVED: "memory",
    EventType.MEMORY_REJECTED: "memory",
    EventType.MEMORY_RETRIEVED: "memory",
    EventType.MEMORY_DELETED: "memory",
    EventType.MCP_RECOVER: "system",
    EventType.PROVIDER_RETRY: "system",
}


def categorize(event_type: EventType) -> str:
    return _CATEGORY_MAP.get(event_type, "other")


def _summarize(event: TraceEvent) -> str:
    data = event.data
    et = event.event_type

    if et == EventType.TOOL_CALL:
        return f"调用工具 {data.get('tool', data.get('name', '?'))}"
    if et == EventType.TOOL_RESULT:
        return f"工具结果 {data.get('tool', '?')}"
    if et in (EventType.GUARD_BLOCK, EventType.GUARD_APPROVED):
        return f"安全策略 {data.get('tool', '?')}: {et.value}"
    if et == EventType.APPROVAL_REQUESTED:
        return f"等待审批 {data.get('tool', '?')}"
    if et == EventType.PLAN_CREATED:
        return "计划已生成，等待确认"
    if et == EventType.PLAN_CONFIRMED:
        return f"计划已确认: {data.get('decision', 'approve')}"
    if et == EventType.SUBAGENT_START:
        return f"子智能体启动 {data.get('name', '?')}"
    if et == EventType.SUBAGENT_END:
        return f"子智能体结束 {data.get('name', '?')}"
    if et == EventType.AGENT_START:
        return f"智能体开始 ({data.get('source', 'user')})"
    if et == EventType.AGENT_END:
        return "智能体结束"
    if et == EventType.THINKING:
        span = data.get("span", "")
        status = data.get("status", "")
        return f"思考 {span} {status}".strip()
    if et == EventType.ERROR:
        return f"错误: {data.get('error', data.get('message', '?'))}"
    if et == EventType.CRON_TRIGGER:
        return f"定时任务 {data.get('action', '')} {data.get('name', data.get('job_id', ''))}".strip()
    if et == EventType.HEARTBEAT:
        return "心跳触发"
    if et == EventType.GATEWAY_MESSAGE:
        return f"网关 {data.get('platform', '?')} {data.get('action', '')}".strip()
    if et in (EventType.MEMORY_PERSIST, EventType.MEMORY_SKIP):
        return "写入长期记忆" if et == EventType.MEMORY_PERSIST else "跳过长期记忆"
    return et.value


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_timeline(trace_id: str) -> dict[str, Any]:
    """Build a structured timeline for a trace_id."""
    events = sorted(trace_store.get_by_trace(trace_id), key=lambda e: e.timestamp)
    start_ts = _parse_ts(events[0].timestamp) if events else None
    prev_ts: datetime | None = None
    items = []
    for idx, e in enumerate(events):
        ts = _parse_ts(e.timestamp)
        offset_ms = int((ts - start_ts).total_seconds() * 1000) if ts and start_ts else 0
        delta_ms = int((ts - prev_ts).total_seconds() * 1000) if ts and prev_ts else 0
        items.append(
            {
                "sequence": idx + 1,
                "id": e.id,
                "timestamp": e.timestamp,
                "category": categorize(e.event_type),
                "event_type": e.event_type.value,
                "run_id": e.run_id,
                "summary": _summarize(e),
                "offset_ms": offset_ms,
                "delta_ms": delta_ms,
                "data": e.data,
            }
        )
        prev_ts = ts or prev_ts
    categories: dict[str, int] = {}
    for item in items:
        cat = str(item["category"])
        categories[cat] = categories.get(cat, 0) + 1

    runs = sorted({e.run_id for e in events if e.run_id})
    end_ts = _parse_ts(events[-1].timestamp) if events else None
    duration_ms = int((end_ts - start_ts).total_seconds() * 1000) if start_ts and end_ts else 0
    return {
        "trace_id": trace_id,
        "event_count": len(items),
        "run_ids": runs,
        "categories": categories,
        "started_at": events[0].timestamp if events else "",
        "ended_at": events[-1].timestamp if events else "",
        "duration_ms": duration_ms,
        "events": items,
    }
