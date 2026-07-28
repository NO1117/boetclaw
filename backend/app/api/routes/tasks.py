"""Task management routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    TaskAttemptResponse,
    TaskCreateRequest,
    TaskEventResponse,
    TaskListResponse,
    TaskQueueControlRequest,
    TaskQueueStatsResponse,
    TaskResponse,
    TaskUpdateRequest,
)
from app.core.agent import agent_manager
from app.core.observability import new_run_id, new_trace_id
from app.services.run_registry import run_registry
from app.services.task_queue.models import TaskStatus as QueueStatus
from app.services.task_scheduler import Task, TaskStatus, task_scheduler

router = APIRouter(prefix="/tasks", tags=["Tasks"])

_SSE_RESET_HEADER = "X-Task-Events-Reset"


def _to_response(task: Task) -> TaskResponse:
    data = task.to_dict()
    return TaskResponse(**data)


async def _ensure_worker() -> None:
    service = task_scheduler.service
    if not service.worker.running:
        service.worker.start()


async def _run_task_direct(task_id: str, trace_id: str, run_id: str) -> None:
    """Legacy immediate execution path used by gateway and explicit /run."""
    task = task_scheduler.get(task_id)
    if not task:
        return
    task_scheduler.update_status(
        task_id,
        TaskStatus.RUNNING,
        expected={TaskStatus.PENDING},
        trace_id=trace_id,
        run_id=run_id,
    )
    try:
        result = await agent_manager.invoke(
            task.prompt,
            task.thread_id,
            trace_id=trace_id,
            run_id=run_id,
            task_id=task.id,
            agent_id=str(task.metadata.get("agent_id", task.agent_id or "default")),
            well_id=str(task.metadata.get("well_id", "")),
        )
        task_scheduler.update_status(
            task_id,
            TaskStatus.COMPLETED,
            expected={TaskStatus.RUNNING},
            result=str(result.get("response", "")),
            trace_id=trace_id,
            run_id=run_id,
        )
    except asyncio.CancelledError:
        task_scheduler.update_status(
            task_id,
            TaskStatus.CANCELLED,
            expected={TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLING},
            trace_id=trace_id,
            run_id=run_id,
        )
        raise
    except Exception as exc:
        task_scheduler.update_status(
            task_id,
            TaskStatus.FAILED,
            expected={TaskStatus.PENDING, TaskStatus.RUNNING},
            error=str(exc),
            trace_id=trace_id,
            run_id=run_id,
        )


def _schedule_task(task_id: str) -> None:
    task = task_scheduler.get(task_id)
    if not task:
        return
    trace_id = new_trace_id()
    run_id = new_run_id()
    agent_id = str(task.metadata.get("agent_id", task.agent_id or "default"))
    task_scheduler.update_status(
        task_id,
        TaskStatus.PENDING,
        expected={
            TaskStatus.PENDING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.INTERRUPTED,
            TaskStatus.DEAD_LETTER,
        },
        trace_id=trace_id,
        run_id=run_id,
    )
    run_registry.start(
        _run_task_direct(task_id, trace_id, run_id),
        agent_id=agent_id,
        thread_id=task.thread_id,
        run_id=run_id,
        task_id=task.id,
        trace_id=trace_id,
    )


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreateRequest, request: Request):
    from app.identity.actor import require_permission
    from app.identity.permissions import TASKS_CREATE
    from app.identity.resource_acl import require_agent_access

    actor = require_permission(request, TASKS_CREATE)
    agent_id = body.agent_id or str((body.metadata or {}).get("agent_id") or "default")
    require_agent_access(request, agent_id, required="runner")
    existing = None
    if body.idempotency_key:
        existing_record = task_scheduler.service.store.find_by_idempotency_key(body.idempotency_key)
        if existing_record:
            existing = Task.from_record(existing_record)
    if existing:
        return _to_response(existing)
    metadata = dict(body.metadata or {})
    if actor.is_user:
        metadata.setdefault("created_by_user_id", actor.user_id)
    task = task_scheduler.create(
        title=body.title,
        prompt=body.prompt,
        gateway=body.gateway,
        gateway_user=body.gateway_user,
        metadata=metadata,
        auto_run=body.auto_run,
        scheduled_at=body.scheduled_at,
        priority=body.priority,
        max_attempts=body.max_attempts,
        idempotency_key=body.idempotency_key,
        agent_id=body.agent_id,
    )
    if body.auto_run and not body.scheduled_at:
        _schedule_task(task.id)
    return _to_response(task)


@router.get("", response_model=list[TaskResponse])
async def list_tasks_legacy(request: Request, status: str | None = None):
    from app.identity.actor import require_actor
    from app.identity.permissions import TASKS_ADMIN
    from app.identity.resource_acl import can_access_agent

    actor = require_actor(request)
    task_status = TaskStatus(status) if status else None
    tasks = task_scheduler.list_tasks(task_status)
    if actor.has(TASKS_ADMIN) or actor.role in {"owner", "admin"} or actor.actor_type in {
        "open",
        "api_token",
        "console_legacy",
    }:
        return [_to_response(t) for t in tasks]
    filtered = []
    for t in tasks:
        created_by = str(t.metadata.get("created_by_user_id", ""))
        if created_by and created_by == actor.user_id:
            filtered.append(t)
            continue
        agent_id = str(t.metadata.get("agent_id", t.agent_id or "default"))
        if can_access_agent(actor, agent_id, required="viewer"):
            filtered.append(t)
    return [_to_response(t) for t in filtered]


@router.get("/list", response_model=TaskListResponse)
async def list_tasks_paged(
    status: str | None = None,
    agent_id: str | None = None,
    source: str | None = None,
    q: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    tasks, next_cursor = task_scheduler.service.list_page(
        status=status,
        agent_id=agent_id,
        source=source,
        query=q,
        created_after=created_after,
        created_before=created_before,
        cursor=cursor,
        limit=limit,
    )
    return TaskListResponse(
        items=[_to_response(Task.from_record(record)) for record in tasks],
        next_cursor=next_cursor,
    )


@router.get("/stats", response_model=TaskQueueStatsResponse)
async def queue_stats():
    stats = task_scheduler.service.queue_stats()
    return TaskQueueStatsResponse(**stats)


@router.post("/queue/control", response_model=TaskQueueStatsResponse)
async def queue_control(request: TaskQueueControlRequest):
    if request.paused:
        task_scheduler.service.pause()
    else:
        task_scheduler.service.resume()
    stats = task_scheduler.service.queue_stats()
    return TaskQueueStatsResponse(**stats)


@router.get("/events/stream")
async def task_events_stream(
    request: Request,
    after_id: int = Query(default=0, ge=0),
    task_id: str | None = None,
):
    service = task_scheduler.service
    latest = service.list_events(task_id=task_id, after_id=0, limit=1)
    max_id = latest[-1].id if latest else 0
    if after_id and max_id - after_id > 5000:
        async def reset_stream():
            payload = {"reset": True, "reason": "cursor_too_old", "max_id": max_id}
            yield f"event: reset\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(reset_stream(), media_type="text/event-stream")

    async def event_generator():
        cursor = after_id
        while True:
            if await request.is_disconnected():
                break
            events = service.list_events(task_id=task_id, after_id=cursor, limit=100)
            for event in events:
                cursor = event.id
                body = TaskEventResponse(**event.to_dict())
                yield f"id: {event.id}\nevent: task\ndata: {body.model_dump_json()}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _require_task(request: Request, task_id: str, *, write: bool = False):
    from app.identity.resource_acl import require_task_access

    task = task_scheduler.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    agent_id = str(task.metadata.get("agent_id", task.agent_id or "default"))
    created_by = str(task.metadata.get("created_by_user_id", ""))
    require_task_access(
        request,
        created_by_user_id=created_by,
        agent_id=agent_id,
        write=write,
    )
    return task


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request):
    task = _require_task(request, task_id, write=False)
    return _to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, body: TaskUpdateRequest, request: Request):
    _require_task(request, task_id, write=True)
    fields: dict[str, Any] = {}
    if body.title is not None:
        fields["title"] = body.title
    if body.prompt is not None:
        fields["prompt"] = body.prompt
    if body.priority is not None:
        fields["priority"] = body.priority
    if body.scheduled_at is not None:
        fields["scheduled_at"] = body.scheduled_at
    if body.max_attempts is not None:
        fields["max_attempts"] = body.max_attempts
    if body.metadata is not None:
        fields["metadata"] = body.metadata
    updated = task_scheduler.service.update_task(task_id, revision=body.revision, fields=fields)
    if not updated:
        current = task_scheduler.get(task_id)
        if not current:
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(status_code=409, detail="Task update conflict or invalid state")
    return _to_response(Task.from_record(updated))


@router.get("/{task_id}/attempts", response_model=list[TaskAttemptResponse])
async def list_attempts(task_id: str, request: Request):
    _require_task(request, task_id, write=False)
    attempts = task_scheduler.service.list_attempts(task_id)
    return [TaskAttemptResponse(**attempt.to_dict()) for attempt in attempts]


@router.get("/{task_id}/events", response_model=list[TaskEventResponse])
async def list_task_events(task_id: str, request: Request, after_id: int = Query(default=0, ge=0)):
    _require_task(request, task_id, write=False)
    events = task_scheduler.service.list_events(task_id=task_id, after_id=after_id)
    return [TaskEventResponse(**event.to_dict()) for event in events]


@router.post("/{task_id}/run", response_model=TaskResponse)
async def run_task(task_id: str, request: Request):
    task = _require_task(request, task_id, write=True)
    if task.status in {TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.LEASED} or (
        task.status == TaskStatus.PENDING and bool(task.run_id)
    ):
        raise HTTPException(status_code=409, detail="Task already running")
    _schedule_task(task_id)
    refreshed = task_scheduler.get(task_id)
    return _to_response(refreshed or task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str, request: Request):
    task = _require_task(request, task_id, write=True)
    if task.status == TaskStatus.CANCELLED:
        return _to_response(task)
    if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.DEAD_LETTER}:
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    task_scheduler.update_status(
        task_id,
        TaskStatus.CANCELLING,
        expected={TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.SCHEDULED},
    )
    await run_registry.cancel(task_id=task_id)
    updated = task_scheduler.update_status(
        task_id,
        TaskStatus.CANCELLED,
        expected={TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.SCHEDULED},
    )
    if not updated:
        current = task_scheduler.get(task_id)
        if current and current.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            raise HTTPException(status_code=409, detail="Task already finished")
        updated = current
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_response(updated)


@router.post("/{task_id}/requeue", response_model=TaskResponse)
async def requeue_task(task_id: str, request: Request):
    _require_task(request, task_id, write=True)
    task = task_scheduler.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in {TaskStatus.DEAD_LETTER, TaskStatus.FAILED, TaskStatus.INTERRUPTED}:
        raise HTTPException(status_code=409, detail="Task cannot be requeued from current status")
    updated = task_scheduler.service.requeue(task_id)
    if not updated:
        raise HTTPException(status_code=409, detail="Requeue failed")
    await _ensure_worker()
    await task_scheduler.service.worker.enqueue_existing(task_id)
    return _to_response(Task.from_record(updated))


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: str):
    return await requeue_task(task_id)
