"""Heartbeat service: periodic self-check that queries the agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import BASE_DIR, settings
from app.core.env_file import update_env_file
from app.core.observability import EventType, emit_event, get_logger

logger = get_logger("heartbeat")

Runner = Callable[..., Awaitable[dict]]
HEARTBEAT_ENV_PATH = BASE_DIR / ".env"
HEARTBEAT_JOB_ID = "heartbeat"


class HeartbeatService:
    """Periodically pings the agent with HEARTBEAT_PROMPT (source=heartbeat)."""

    def __init__(self, env_path: Path | None = None) -> None:
        self._scheduler: Any = None
        self.runner: Runner | None = None
        self.last_channel: str = ""
        self.last_chat_id: str = ""
        self._env_path = env_path or HEARTBEAT_ENV_PATH

    @property
    def enabled(self) -> bool:
        return settings.heartbeat_enabled

    def config(self) -> dict[str, Any]:
        return {
            "enabled": settings.heartbeat_enabled,
            "interval_minutes": settings.heartbeat_interval_minutes,
            "prompt": settings.heartbeat_prompt,
            "last_channel": self.last_channel,
            "persisted": True,
        }

    def start(self, scheduler: Any = None) -> None:
        if scheduler is not None:
            self._scheduler = scheduler
        elif self._scheduler is None:
            try:
                from apscheduler.schedulers.asyncio import AsyncIOScheduler

                self._scheduler = AsyncIOScheduler(timezone="UTC")
                self._scheduler.start()
            except Exception as exc:  # noqa: BLE001
                logger.warning("heartbeat_start_failed", error=str(exc))
                return
        self._apply_schedule()

    def update(
        self,
        *,
        enabled: bool | None = None,
        interval_minutes: int | None = None,
        prompt: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        if enabled is not None:
            settings.heartbeat_enabled = bool(enabled)
        if interval_minutes is not None:
            settings.heartbeat_interval_minutes = max(1, int(interval_minutes))
        if prompt is not None:
            settings.heartbeat_prompt = prompt
        if persist:
            self._persist_settings()
        self._apply_schedule()
        return self.config()

    def _persist_settings(self) -> None:
        update_env_file(
            {
                "HEARTBEAT_ENABLED": "true" if settings.heartbeat_enabled else "false",
                "HEARTBEAT_INTERVAL_MINUTES": str(settings.heartbeat_interval_minutes),
                "HEARTBEAT_PROMPT": settings.heartbeat_prompt,
            },
            self._env_path,
        )

    def _apply_schedule(self) -> None:
        if self._scheduler is None:
            if settings.heartbeat_enabled:
                logger.info("heartbeat_deferred", reason="scheduler_not_ready")
            else:
                logger.info("heartbeat_disabled")
            return
        try:
            self._scheduler.remove_job(HEARTBEAT_JOB_ID)
        except Exception:  # noqa: BLE001
            pass
        if not settings.heartbeat_enabled:
            logger.info("heartbeat_disabled")
            return
        self._scheduler.add_job(
            self._beat,
            trigger="interval",
            minutes=max(1, settings.heartbeat_interval_minutes),
            id=HEARTBEAT_JOB_ID,
            replace_existing=True,
        )
        logger.info("heartbeat_started", interval=settings.heartbeat_interval_minutes)

    async def _beat(self) -> None:
        emit_event(EventType.HEARTBEAT, {"action": "fire", "prompt": settings.heartbeat_prompt[:50]})
        try:
            result = await self._invoke(settings.heartbeat_prompt)
            response = str(result.get("response", ""))
            await self._maybe_reply(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("heartbeat_run_failed", error=str(exc))

    async def _invoke(self, prompt: str) -> dict:
        if self.runner is not None:
            return await self.runner(prompt, source="heartbeat")
        import uuid

        from app.core.agent import agent_manager

        return await agent_manager.invoke(prompt, uuid.uuid4().hex[:16], source="heartbeat")

    async def _maybe_reply(self, response: str) -> None:
        if not self.last_channel or not response:
            return
        from app.services.gateway.base import GatewayMessage
        from app.services.gateway.manager import channel_manager

        channel = channel_manager.get(self.last_channel)
        if channel is None:
            return
        msg = GatewayMessage(
            platform=self.last_channel,
            user_id="",
            user_name="heartbeat",
            content=settings.heartbeat_prompt,
            message_id="",
            chat_id=self.last_chat_id,
        )
        await channel.send_reply(msg, response)


heartbeat_service = HeartbeatService()
