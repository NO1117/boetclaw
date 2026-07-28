"""User memory management API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.memory.models import MemorySearchFilters
from app.memory.service import MemoryUnavailableError, memory_service

router = APIRouter(prefix="/memories", tags=["Memories"])


class MemoryCreateRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    scope: str = "agent"
    thread_id: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "active"


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    scope: str | None = None
    thread_id: str | None = None
    status: str | None = None


class BulkDeleteRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    status: str = ""
    scope: str = ""
    thread_id: str = ""
    ids: list[str] = Field(default_factory=list)


def _memory_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MemoryUnavailableError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="记忆操作失败")


@router.get("")
async def list_memories(
    agent_id: str = Query(..., min_length=1),
    q: str = "",
    scope: str = "",
    status: str = "",
    thread_id: str = "",
    tag: str = "",
    page: int = 1,
    page_size: int = 20,
):
    try:
        return memory_service.list_memories(
            agent_id,
            filters=MemorySearchFilters(q=q, scope=scope, status=status, thread_id=thread_id, tag=tag),
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        raise _memory_error(exc) from exc


@router.post("")
async def create_memory(body: MemoryCreateRequest):
    try:
        record = memory_service.create_manual(
            agent_id=body.agent_id,
            content=body.content,
            scope=body.scope,
            thread_id=body.thread_id,
            tags=body.tags,
            status=body.status,
        )
        return record.to_public_dict()
    except Exception as exc:
        raise _memory_error(exc) from exc


@router.get("/export")
async def export_memories(agent_id: str = Query(..., min_length=1)):
    try:
        return memory_service.export_memories(agent_id)
    except Exception as exc:
        raise _memory_error(exc) from exc


@router.get("/health")
async def memory_health():
    from app.memory.metrics import memory_metrics

    return {"health": memory_service.health(), "metrics": memory_metrics.snapshot()}


@router.post("/bulk-delete")
async def bulk_delete_memories(body: BulkDeleteRequest):
    try:
        count = memory_service.bulk_delete(
            body.agent_id,
            status=body.status,
            scope=body.scope,
            thread_id=body.thread_id,
            ids=body.ids or None,
        )
        return {"deleted": count}
    except Exception as exc:
        raise _memory_error(exc) from exc


@router.get("/{memory_id}")
async def get_memory(memory_id: str, agent_id: str = Query(..., min_length=1)):
    try:
        record = memory_service.get(agent_id, memory_id)
    except Exception as exc:
        raise _memory_error(exc) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return record.to_public_dict()


@router.patch("/{memory_id}")
async def update_memory(memory_id: str, body: MemoryUpdateRequest, agent_id: str = Query(..., min_length=1)):
    try:
        record = memory_service.update_memory(
            agent_id,
            memory_id,
            content=body.content,
            tags=body.tags,
            scope=body.scope,
            thread_id=body.thread_id,
            status=body.status,
        )
        return record.to_public_dict()
    except Exception as exc:
        raise _memory_error(exc) from exc


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, agent_id: str = Query(..., min_length=1)):
    try:
        ok = memory_service.delete(agent_id, memory_id)
    except Exception as exc:
        raise _memory_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"deleted": True, "memory_id": memory_id}


@router.post("/{memory_id}/approve")
async def approve_memory(memory_id: str, agent_id: str = Query(..., min_length=1)):
    try:
        record = memory_service.approve(agent_id, memory_id)
        return record.to_public_dict()
    except Exception as exc:
        raise _memory_error(exc) from exc


@router.post("/{memory_id}/reject")
async def reject_memory(memory_id: str, agent_id: str = Query(..., min_length=1)):
    try:
        record = memory_service.reject(agent_id, memory_id)
        return record.to_public_dict()
    except Exception as exc:
        raise _memory_error(exc) from exc
