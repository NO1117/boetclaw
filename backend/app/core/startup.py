"""Two-phase startup orchestration.

Phase 1: fast, in-process manager instantiation (no network IO) -> service ready.
Phase 2: background heavy init (MCP connect, agent build).
"""

from __future__ import annotations

import time
from typing import Any

from app.core.observability import get_logger

logger = get_logger("startup")


async def phase1_fast(app: Any) -> None:
    """Synchronous fast path; target < 1s. Only in-memory setup."""
    t = time.perf_counter()
    from app.core.config import settings

    settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    from app.core.checkpoint import checkpoint_provider

    try:
        await checkpoint_provider.initialize()
        app.state.checkpoint_ready = True
    except Exception as exc:  # noqa: BLE001
        app.state.checkpoint_ready = False
        logger.error("checkpoint_init_failed", error=str(exc))

    if checkpoint_provider.backend == "memory":
        from app.security.approval import approval_service

        expired = approval_service.expire_pending_for_restart("memory")
        if expired:
            logger.warning("memory_checkpoint_pending_expired", count=expired)

    # Register channels and start queue consumers (in-memory, no network IO).
    from app.api.routes import gateway as gateway_route  # noqa: F401  (binds handler)
    from app.services.gateway.manager import channel_manager

    channel_manager.bootstrap_from_settings()
    await channel_manager.start()

    # Discover plugins (safe default: only config-enabled ones load their tools).
    from app.plugins.loader import discover_and_load

    discover_and_load()

    app.state.ready = True
    app.state.agent_ready = False
    elapsed_ms = (time.perf_counter() - t) * 1000
    logger.info("phase1_done", elapsed_ms=round(elapsed_ms, 2))


async def phase2_background(app: Any) -> None:
    """Background heavy init: MCP + agent build. Errors are logged, not fatal."""
    t = time.perf_counter()
    try:
        from app.core.agent import agent_manager
        from app.tools.mcp_manager import mcp_manager

        await mcp_manager.connect()
        await agent_manager.initialize()
        app.state.agent_ready = True

        # Start schedulers after the agent is ready so triggers can run.
        from app.services.cron_service import cron_service
        from app.services.heartbeat import heartbeat_service

        cron_service.start()
        heartbeat_service.start(scheduler=cron_service._scheduler)

        logger.info("phase2_done", elapsed_ms=round((time.perf_counter() - t) * 1000, 2))
    except Exception as exc:  # noqa: BLE001
        logger.error("phase2_failed", error=str(exc))
        app.state.agent_ready = False
