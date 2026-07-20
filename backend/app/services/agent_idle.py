"""Periodic eviction for loaded idle workspace agents."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from app.agents.multi_agent_manager import multi_agent_manager
from app.core.config import settings
from app.core.observability import get_logger

logger = get_logger("agent_idle")


class AgentIdleEvictionService:
    def __init__(self, manager: Any = multi_agent_manager) -> None:
        self.manager = manager
        self._task: asyncio.Task | None = None
        self._interval_seconds: float = 60.0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, interval_seconds: float | None = None) -> None:
        if self.running:
            return
        ttl_seconds = max(settings.agent_idle_ttl_minutes, 0) * 60
        self._interval_seconds = interval_seconds or max(60.0, min(float(ttl_seconds or 60), 300.0))
        self._task = asyncio.create_task(self._loop())
        logger.info("agent_idle_eviction_started", interval_seconds=self._interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("agent_idle_eviction_stopped")

    def run_once(self) -> list[str]:
        return self.manager.evict_idle()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            evicted = self.run_once()
            if evicted:
                logger.info("agent_idle_eviction_run", evicted=evicted)


agent_idle_eviction_service = AgentIdleEvictionService()
