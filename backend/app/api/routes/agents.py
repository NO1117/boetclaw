"""Multi-agent workspace management routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from app.agents.multi_agent_manager import multi_agent_manager
from app.memory.session_store import session_store
from app.services.task_scheduler import task_scheduler

router = APIRouter(prefix="/agents", tags=["Agents"])


class CreateAgentRequest(BaseModel):
    agent_id: str
    config: dict = {}


class DeleteAgentBody(BaseModel):
    purge: bool = False


@router.get("")
async def list_agents():
    return {"agents": [ws.to_dict() for ws in multi_agent_manager.list_agents()]}


@router.post("")
async def create_agent(body: CreateAgentRequest):
    ws = multi_agent_manager.create(body.agent_id, body.config)
    return ws.to_dict()


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return ws.to_dict()


@router.get("/{agent_id}/files")
async def list_agent_files(agent_id: str):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    files_dir = ws.files_dir()
    rows = []
    if files_dir.exists():
        for path in files_dir.rglob("*"):
            if not path.is_file():
                continue
            stat = path.stat()
            rows.append(
                {
                    "path": str(path.relative_to(files_dir)).replace("\\", "/"),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
    rows.sort(key=lambda row: row["modified_at"], reverse=True)
    return {"agent_id": agent_id, "root": str(files_dir), "files": rows}


@router.get("/{agent_id}/history")
async def agent_history(agent_id: str, limit: int = 50):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")

    entries = []
    for task in task_scheduler.list_tasks():
        match_source = ""
        if task.metadata.get("agent_id") == agent_id:
            match_source = "task.metadata.agent_id"
        elif agent_id != "default" and agent_id in task.title:
            match_source = "task.title"
        if match_source:
            entries.append(
                {
                    "type": "task",
                    "id": task.id,
                    "title": task.title,
                    "status": task.status.value,
                    "thread_id": task.thread_id,
                    "trace_id": task.trace_id,
                    "run_id": task.run_id,
                    "updated_at": task.updated_at,
                    "match_source": match_source,
                }
            )

    for session in session_store.list_sessions(limit=500):
        if session.get("agent_id") == agent_id:
            entries.append(
                {
                    "type": "session",
                    "id": session["thread_id"],
                    "title": session.get("title", session["thread_id"]),
                    "status": "recorded",
                    "thread_id": session["thread_id"],
                    "trace_id": session.get("last_trace_id", ""),
                    "run_id": session.get("last_run_id", ""),
                    "updated_at": session.get("updated_at", ""),
                    "match_source": "session.agent_id",
                }
            )

    entries.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    return {"agent_id": agent_id, "history": entries[:limit]}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    purge: bool = Query(False, description="true 时删除工作区目录并清理 checkpoint"),
    body: DeleteAgentBody | None = Body(None),
):
    do_purge = purge or (body.purge if body is not None else False)
    try:
        ok = await multi_agent_manager.delete(agent_id, purge=do_purge)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="agent not found")
    if do_purge:
        return {
            "deleted": agent_id,
            "purged": True,
            "checkpoint_retained": False,
            "detail": "已彻底清除工作区目录与 checkpoint；不可再 resume",
        }
    return {
        "deleted": agent_id,
        "purged": False,
        "checkpoint_retained": True,
        "detail": "仅注销 Agent；checkpoint 数据保留，列表不可见且不可 resume",
    }
