"""Cron & heartbeat scheduling routes (registered before /tasks/{id})."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.schemas import CronJobCreateRequest, HeartbeatUpdateRequest
from app.services.cron_service import cron_service
from app.services.heartbeat import heartbeat_service

router = APIRouter(prefix="/tasks", tags=["Scheduling"])


class CronJobUpdateRequest(BaseModel):
    name: str | None = None
    cron: str | None = None
    prompt: str | None = None
    channel: str | None = None
    chat_id: str | None = None
    agent_id: str | None = None
    enabled: bool | None = None


class CronEnableRequest(BaseModel):
    enabled: bool


@router.get("/cron")
async def list_cron_jobs():
    return {"jobs": [j.to_dict() for j in cron_service.list_jobs()]}


@router.post("/cron")
async def create_cron_job(body: CronJobCreateRequest):
    try:
        job = cron_service.add_job(
            name=body.name,
            cron=body.cron,
            prompt=body.prompt,
            channel=body.channel,
            chat_id=body.chat_id,
            agent_id=body.agent_id,
            enabled=body.enabled,
        )
    except Exception as exc:  # invalid crontab etc.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.to_dict()


@router.delete("/cron/{job_id}")
async def delete_cron_job(job_id: str):
    if not cron_service.remove(job_id):
        raise HTTPException(status_code=404, detail="cron job not found")
    return {"deleted": job_id}


@router.put("/cron/{job_id}")
async def update_cron_job(job_id: str, body: CronJobUpdateRequest):
    try:
        job = cron_service.update_job(job_id, **body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="cron job not found")
    return job.to_dict()


@router.post("/cron/{job_id}/enable")
async def enable_cron_job(job_id: str, body: CronEnableRequest):
    job = cron_service.set_enabled(job_id, body.enabled)
    if job is None:
        raise HTTPException(status_code=404, detail="cron job not found")
    return job.to_dict()


@router.post("/cron/{job_id}/trigger")
async def trigger_cron_job(job_id: str):
    record = await cron_service.trigger(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="cron job not found or disabled")
    return record.to_dict()


@router.get("/cron/history")
async def cron_history(job_id: str = "", limit: int = 100):
    return {"history": [r.to_dict() for r in cron_service.history(job_id, limit)]}


@router.get("/heartbeat")
async def get_heartbeat():
    return heartbeat_service.config()


@router.put("/heartbeat")
async def update_heartbeat(body: HeartbeatUpdateRequest):
    return heartbeat_service.update(
        enabled=body.enabled,
        interval_minutes=body.interval_minutes,
        prompt=body.prompt,
        persist=True,
    )
