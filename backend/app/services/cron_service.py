"""Cron scheduling service: APScheduler-driven jobs with JSON persistence."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger

logger = get_logger("cron")

# runner(prompt, *, source, agent_id) -> awaitable[dict]
JobRunner = Callable[..., Awaitable[dict]]


@dataclass
class CronJob:
    id: str
    name: str
    cron: str
    prompt: str
    channel: str = ""
    chat_id: str = ""
    agent_id: str = "default"
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run: str = ""
    last_status: str = ""
    last_error: str = ""
    run_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CronRunRecord:
    id: str
    job_id: str
    job_name: str
    status: str
    started_at: str
    finished_at: str = ""
    trace_id: str = ""
    run_id: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CronService:
    """Manages cron jobs backed by an AsyncIOScheduler."""

    HISTORY_LIMIT = 500

    def __init__(
        self,
        store_path: Path | None = None,
        history_path: Path | None = None,
    ) -> None:
        self._jobs: dict[str, CronJob] = {}
        self._scheduler: Any = None
        self._store = store_path or (settings.workspace_dir / ".cache" / "cron_jobs.json")
        self._history_store = history_path or (
            settings.workspace_dir / ".cache" / "cron_history.json"
        )
        self.runner: JobRunner | None = None
        self._history: list[CronRunRecord] = []
        self._load()
        self._load_history()

    # ----- persistence -----
    def _load(self) -> None:
        if self._store.exists():
            try:
                data = json.loads(self._store.read_text(encoding="utf-8"))
                for item in data:
                    job = CronJob(**item)
                    self._jobs[job.id] = job
            except Exception as exc:  # noqa: BLE001
                logger.warning("cron_load_failed", error=str(exc))

    def _persist(self) -> None:
        self._store.parent.mkdir(parents=True, exist_ok=True)
        self._store.write_text(
            json.dumps([j.to_dict() for j in self._jobs.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_history(self) -> None:
        if not self._history_store.exists():
            return
        try:
            data = json.loads(self._history_store.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            rows: list[CronRunRecord] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    rows.append(CronRunRecord(**item))
                except TypeError:
                    continue
            self._history = rows[: self.HISTORY_LIMIT]
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_history_load_failed", error=str(exc))

    def _persist_history(self) -> None:
        self._history_store.parent.mkdir(parents=True, exist_ok=True)
        self._history_store.write_text(
            json.dumps(
                [r.to_dict() for r in self._history[: self.HISTORY_LIMIT]],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ----- lifecycle -----
    def start(self) -> None:
        if self._scheduler is not None:
            return
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler(timezone="UTC")
            self._scheduler.start()
            for job in self._jobs.values():
                if job.enabled:
                    self._schedule(job)
            logger.info("cron_started", jobs=len(self._jobs))
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_start_failed", error=str(exc))

    def shutdown(self) -> None:
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                pass
            self._scheduler = None

    def _schedule(self, job: CronJob) -> None:
        if self._scheduler is None:
            return
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(job.cron, timezone="UTC")
        self._scheduler.add_job(
            self._run_job, trigger=trigger, id=job.id, args=[job.id], replace_existing=True
        )

    # ----- CRUD -----
    def add_job(
        self,
        name: str,
        cron: str,
        prompt: str,
        *,
        channel: str = "",
        chat_id: str = "",
        agent_id: str = "default",
        enabled: bool = True,
    ) -> CronJob:
        job = CronJob(
            id=uuid.uuid4().hex[:12],
            name=name,
            cron=cron,
            prompt=prompt,
            channel=channel,
            chat_id=chat_id,
            agent_id=agent_id,
            enabled=enabled,
        )
        self._jobs[job.id] = job
        self._persist()
        if enabled and self._scheduler is not None:
            self._schedule(job)
        emit_event(EventType.CRON_TRIGGER, {"action": "add", "job_id": job.id, "cron": cron})
        return job

    def remove(self, job_id: str) -> bool:
        job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        self._persist()
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:  # noqa: BLE001
                pass
        return True

    def update_job(self, job_id: str, **changes: Any) -> CronJob | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        for key in ("name", "cron", "prompt", "channel", "chat_id", "agent_id"):
            if key in changes and changes[key] is not None:
                setattr(job, key, changes[key])
        if "enabled" in changes and changes["enabled"] is not None:
            job.enabled = bool(changes["enabled"])
        self._persist()
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
            if job.enabled:
                self._schedule(job)
        return job

    def set_enabled(self, job_id: str, enabled: bool) -> CronJob | None:
        return self.update_job(job_id, enabled=enabled)

    def list_jobs(self) -> list[CronJob]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    def history(self, job_id: str = "", limit: int = 100) -> list[CronRunRecord]:
        rows = [r for r in self._history if not job_id or r.job_id == job_id]
        return rows[:limit]

    async def trigger(self, job_id: str) -> CronRunRecord | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return await self._run_job(job_id, manual=True)

    # ----- execution -----
    async def _run_job(self, job_id: str, manual: bool = False) -> CronRunRecord | None:
        job = self._jobs.get(job_id)
        if job is None or not job.enabled:
            return None
        started = datetime.now(timezone.utc).isoformat()
        record = CronRunRecord(id=uuid.uuid4().hex[:12], job_id=job.id, job_name=job.name, status="running", started_at=started)
        self._history.insert(0, record)
        self._history = self._history[: self.HISTORY_LIMIT]
        self._persist_history()
        emit_event(EventType.CRON_TRIGGER, {"action": "manual_fire" if manual else "fire", "job_id": job_id, "name": job.name})
        job.last_run = started
        job.run_count += 1
        try:
            result = await self._invoke(job.prompt, agent_id=job.agent_id)
            response = str(result.get("response", ""))
            await self._maybe_reply(job, response)
            record.status = "success"
            record.trace_id = str(result.get("trace_id", ""))
            record.run_id = str(result.get("run_id", ""))
            job.last_status = "success"
            job.last_error = ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("cron_run_failed", job_id=job_id, error=str(exc))
            record.status = "failed"
            record.error = str(exc)
            job.last_status = "failed"
            job.last_error = str(exc)
        finally:
            record.finished_at = datetime.now(timezone.utc).isoformat()
            self._persist()
            self._persist_history()
        return record

    async def _invoke(self, prompt: str, *, agent_id: str) -> dict:
        if self.runner is not None:
            return await self.runner(prompt, source="cron", agent_id=agent_id)
        import uuid as _uuid

        thread_id = _uuid.uuid4().hex[:16]
        if agent_id and agent_id != "default":
            from app.agents.resolver import resolve_agent_graph
            from app.agents.runtime import invoke_agent

            graph = await resolve_agent_graph(agent_id)
            return await invoke_agent(graph, prompt, thread_id, agent_id=agent_id, source="cron")
        from app.core.agent import agent_manager

        return await agent_manager.invoke(prompt, thread_id, source="cron")

    async def _maybe_reply(self, job: CronJob, response: str) -> None:
        if not job.channel or not response:
            return
        from app.services.gateway.base import GatewayMessage
        from app.services.gateway.manager import channel_manager

        channel = channel_manager.get(job.channel)
        if channel is None:
            return
        msg = GatewayMessage(
            platform=job.channel,
            user_id="",
            user_name="cron",
            content=job.prompt,
            message_id="",
            chat_id=job.chat_id,
            is_group=bool(job.chat_id),
        )
        await channel.send_reply(msg, response)


cron_service = CronService()
