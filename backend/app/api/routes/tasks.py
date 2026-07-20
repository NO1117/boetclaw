"""Task management routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.api.schemas import TaskCreateRequest, TaskResponse
from app.core.agent import agent_manager
from app.core.observability import new_run_id, new_trace_id
from app.services.run_registry import run_registry
from app.services.task_scheduler import TaskStatus, task_scheduler

router = APIRouter(prefix="/tasks", tags=["Tasks"])


async def _run_task(task_id: str, trace_id: str, run_id: str) -> None:
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
            agent_id=str(task.metadata.get("agent_id", "default")),
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
    agent_id = str(task.metadata.get("agent_id", "default"))
    task_scheduler.update_status(
        task_id,
        TaskStatus.PENDING,
        expected={TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
        trace_id=trace_id,
        run_id=run_id,
    )
    run_registry.start(
        _run_task(task_id, trace_id, run_id),
        agent_id=agent_id,
        thread_id=task.thread_id,
        run_id=run_id,
        task_id=task.id,
        trace_id=trace_id,
    )


@router.post("", response_model=TaskResponse)
async def create_task(request: TaskCreateRequest):
    task = task_scheduler.create(
        title=request.title,
        prompt=request.prompt,
        gateway=request.gateway,
        gateway_user=request.gateway_user,
        metadata=request.metadata,
    )
    if request.auto_run:
        _schedule_task(task.id)
    return TaskResponse(**task.to_dict())


@router.get("", response_model=list[TaskResponse])
async def list_tasks(status: str | None = None):
    task_status = TaskStatus(status) if status else None
    tasks = task_scheduler.list_tasks(task_status)
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    task = task_scheduler.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**task.to_dict())


@router.post("/{task_id}/run", response_model=TaskResponse)
async def run_task(task_id: str):
    task = task_scheduler.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in {TaskStatus.RUNNING, TaskStatus.CANCELLING} or (
        task.status == TaskStatus.PENDING and bool(task.run_id)
    ):
        raise HTTPException(status_code=409, detail="Task already running")
    _schedule_task(task_id)
    return TaskResponse(**task.to_dict())


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str):
    task = task_scheduler.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.CANCELLED:
        return TaskResponse(**task.to_dict())
    if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
        raise HTTPException(status_code=409, detail=f"Task already {task.status.value}")
    task_scheduler.update_status(
        task_id,
        TaskStatus.CANCELLING,
        expected={TaskStatus.PENDING, TaskStatus.RUNNING},
    )
    result = await run_registry.cancel(task_id=task_id)
    if not result.cancelled:
        current = task_scheduler.get(task_id)
        if current and current.status != TaskStatus.CANCELLED:
            raise HTTPException(status_code=409, detail=result.detail)
    task_scheduler.update_status(
        task_id,
        TaskStatus.CANCELLED,
        expected={TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLING},
    )
    return TaskResponse(**task.to_dict())
