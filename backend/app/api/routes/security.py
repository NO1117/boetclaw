"""Security & approval routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.schemas import ApprovalResumeRequest
from app.security.approval import approval_service
from app.security.engine import get_guard_engine, reload_guard_engine

router = APIRouter(prefix="/security", tags=["Security"])


class GuardConfigUpdate(BaseModel):
    level: str


@router.get("/config")
async def get_config(request: Request):
    from app.identity.actor import require_actor

    require_actor(request)
    engine = get_guard_engine()
    return {"enabled": engine.enabled, "level": engine.level.value}


@router.put("/config")
async def update_config(body: GuardConfigUpdate, request: Request):
    from app.core.config import settings
    from app.identity.actor import require_permission
    from app.identity.permissions import SECURITY_SETTINGS

    require_permission(request, SECURITY_SETTINGS)
    settings.tool_guard_level = body.level
    engine = reload_guard_engine()
    return {"enabled": engine.enabled, "level": engine.level.value}


def _approval_agent_id(row) -> str:
    if row.execution_ref is not None and row.execution_ref.agent_id:
        return row.execution_ref.agent_id
    return "default"


@router.get("/approvals")
async def list_approvals(request: Request):
    from app.identity.actor import require_actor
    from app.identity.resource_acl import can_access_agent

    actor = require_actor(request)
    pending = approval_service.list_attention()
    if actor.is_open or actor.actor_type in {"api_token", "console_legacy"} or actor.role in {
        "owner",
        "admin",
    }:
        return {"pending": [r.to_dict() for r in pending]}
    visible = [
        r for r in pending if can_access_agent(actor, _approval_agent_id(r), required="runner")
    ]
    return {"pending": [r.to_dict() for r in visible]}


@router.get("/approvals/history")
async def list_approval_history(request: Request):
    from app.identity.actor import require_actor
    from app.identity.resource_acl import can_access_agent

    actor = require_actor(request)
    rows = approval_service.list_all()
    if actor.is_open or actor.actor_type in {"api_token", "console_legacy"} or actor.role in {
        "owner",
        "admin",
    }:
        return {"approvals": [r.to_dict() for r in rows]}
    visible = [
        r for r in rows if can_access_agent(actor, _approval_agent_id(r), required="viewer")
    ]
    return {"approvals": [r.to_dict() for r in visible]}


@router.post("/approvals/resume")
async def resume_approval(body: ApprovalResumeRequest, request: Request):
    from app.identity.resource_acl import require_agent_access
    from app.services.approval_resume import approval_resume_service
    from app.services.execution_resume import ResumeValidationError

    approval = approval_service.get(body.approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Not found")
    agent_id = _approval_agent_id(approval)
    if body.execution_ref is not None and getattr(body.execution_ref, "agent_id", None):
        agent_id = body.execution_ref.agent_id
    require_agent_access(request, agent_id, required="runner")
    try:
        return await approval_resume_service.resume(
            approval_id=body.approval_id,
            execution_ref=body.execution_ref,
            thread_id=body.thread_id or "",
            decision=body.decision,
        )
    except ResumeValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
