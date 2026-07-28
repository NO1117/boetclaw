"""Multi-agent workspace management routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.agents.multi_agent_manager import multi_agent_manager
from app.agents.profile.metrics import profile_metrics
from app.agents.profile.security import ProfileSecurityError
from app.agents.profile.service import profile_service
from app.agents.profile.store import ProfileConflictError, ProfileStoreError
from app.agents.profile.validator import ProfileValidationError
from app.memory.session_store import session_store
from app.services.task_scheduler import task_scheduler

router = APIRouter(prefix="/agents", tags=["Agents"])


class CreateAgentRequest(BaseModel):
    agent_id: str
    config: dict = Field(default_factory=dict)
    profile: dict[str, Any] | None = None


class DeleteAgentBody(BaseModel):
    purge: bool = False


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    profile: dict[str, Any]


class ProfileValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int | None = None
    profile: dict[str, Any]


class ProfileRollbackRequest(BaseModel):
    target_revision: int
    confirm: bool = False


class CloneAgentRequest(BaseModel):
    new_agent_id: str | None = None
    copy_skills: bool = False


class ImportAgentRequest(BaseModel):
    agent_id: str | None = None
    payload: dict[str, Any]


def _raise_store_error(exc: ProfileStoreError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _raise_validation_error(exc: ProfileValidationError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"message": str(exc), "errors": exc.errors}) from exc


@router.get("")
async def list_agents(request: Request):
    from app.identity.actor import require_actor
    from app.identity.resource_acl import filter_agents_for_actor

    actor = require_actor(request)
    agents = multi_agent_manager.list_agents()
    allowed = set(filter_agents_for_actor(actor, [ws.agent_id for ws in agents]))
    return {"agents": [ws.to_dict() for ws in agents if ws.agent_id in allowed]}


@router.post("")
async def create_agent(body: CreateAgentRequest, request: Request):
    from app.identity.actor import require_permission
    from app.identity.permissions import AGENTS_CREATE
    from app.identity.service import identity_service

    actor = require_permission(request, AGENTS_CREATE)
    try:
        ws = multi_agent_manager.create(body.agent_id, body.config)
        if body.profile:
            await profile_service.apply_profile(
                body.agent_id,
                body.profile,
                expected_revision=profile_service.get_or_create(body.agent_id).revision,
            )
        identity_service.ensure_resource(
            "agent",
            body.agent_id,
            owner_user_id=actor.user_id if actor.is_user else "",
            visibility="workspace",
        )
        return ws.to_dict()
    except ProfileSecurityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.post("/import")
async def import_agent(body: ImportAgentRequest):
    try:
        response = await profile_service.import_profile(body.payload, agent_id=body.agent_id, operator="api")
        return response.model_dump()
    except ProfileSecurityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.get("/profile/metrics")
async def agent_profile_metrics():
    return profile_metrics.snapshot()


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    from app.identity.resource_acl import require_agent_access

    require_agent_access(request, agent_id, required="viewer")
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return ws.to_dict()


@router.get("/{agent_id}/files")
async def list_agent_files(agent_id: str, request: Request):
    from app.identity.resource_acl import require_agent_access

    require_agent_access(request, agent_id, required="viewer")
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
async def agent_history(agent_id: str, request: Request, limit: int = 50):
    from app.identity.resource_acl import require_agent_access

    require_agent_access(request, agent_id, required="viewer")
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
    request: Request,
    purge: bool = Query(False, description="true 时删除工作区目录并清理 checkpoint"),
    body: DeleteAgentBody | None = Body(None),
):
    from app.identity.resource_acl import require_agent_access

    require_agent_access(request, agent_id, required="editor")
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


@router.get("/{agent_id}/profile")
async def get_agent_profile(agent_id: str, request: Request):
    from app.identity.resource_acl import require_agent_access

    require_agent_access(request, agent_id, required="viewer")
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        return profile_service.build_response(profile_service.get_or_create(agent_id)).model_dump()
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.put("/{agent_id}/profile")
async def update_agent_profile(agent_id: str, body: ProfileUpdateRequest, request: Request):
    from app.identity.resource_acl import require_agent_access

    require_agent_access(request, agent_id, required="editor")
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        response = await profile_service.apply_profile(
            agent_id,
            body.profile,
            expected_revision=body.revision,
            operator="api",
        )
        return response.model_dump()
    except ProfileConflictError as exc:
        profile_metrics.record_conflict()
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "expected_revision": exc.expected_revision, "actual_revision": exc.actual_revision},
        ) from exc
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.post("/{agent_id}/profile/validate")
async def validate_agent_profile(agent_id: str, body: ProfileValidateRequest):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        result = profile_service.validate_payload(
            agent_id,
            body.profile,
            expected_revision=body.revision,
        )
        return result.model_dump()
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.get("/{agent_id}/profile/versions")
async def list_agent_profile_versions(agent_id: str, offset: int = 0, limit: int = Query(20, ge=1, le=100)):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return profile_service.list_versions(agent_id, offset=offset, limit=limit)


@router.get("/{agent_id}/profile/versions/{revision}")
async def get_agent_profile_version(agent_id: str, revision: int):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        return profile_service.get_version_detail(agent_id, revision)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.post("/{agent_id}/profile/rollback")
async def rollback_agent_profile(agent_id: str, body: ProfileRollbackRequest):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="回滚需要 confirm=true")
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        response = await profile_service.rollback(agent_id, body.target_revision, operator="api")
        return response.model_dump()
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.post("/{agent_id}/clone")
async def clone_agent(agent_id: str, body: CloneAgentRequest | None = Body(None)):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    payload = body or CloneAgentRequest()
    try:
        response = await profile_service.clone_agent(
            agent_id,
            new_agent_id=payload.new_agent_id,
            copy_skills=payload.copy_skills,
            operator="api",
        )
        return response.model_dump()
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)


@router.get("/{agent_id}/export")
async def export_agent(agent_id: str):
    ws = multi_agent_manager.get_workspace(agent_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        return profile_service.export_profile(agent_id)
    except ProfileValidationError as exc:
        _raise_validation_error(exc)
    except ProfileStoreError as exc:
        _raise_store_error(exc)
