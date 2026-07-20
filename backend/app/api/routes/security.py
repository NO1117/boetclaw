"""Security & approval routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.schemas import ApprovalResumeRequest
from app.security.approval import approval_service
from app.security.engine import get_guard_engine, reload_guard_engine

router = APIRouter(prefix="/security", tags=["Security"])


class GuardConfigUpdate(BaseModel):
    level: str


@router.get("/config")
async def get_config():
    engine = get_guard_engine()
    return {"enabled": engine.enabled, "level": engine.level.value}


@router.put("/config")
async def update_config(body: GuardConfigUpdate):
    from app.core.config import settings

    settings.tool_guard_level = body.level
    engine = reload_guard_engine()
    return {"enabled": engine.enabled, "level": engine.level.value}


@router.get("/approvals")
async def list_approvals():
    return {"pending": [r.to_dict() for r in approval_service.list_attention()]}


@router.get("/approvals/history")
async def list_approval_history():
    return {"approvals": [r.to_dict() for r in approval_service.list_all()]}


@router.post("/approvals/resume")
async def resume_approval(body: ApprovalResumeRequest):
    from app.services.approval_resume import approval_resume_service
    from app.services.execution_resume import ResumeValidationError

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
