"""BoetClaw FastAPI application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    agent,
    agents,
    auth,
    cron,
    domain,
    files,
    gateway,
    monitor,
    plugins,
    providers,
    security,
    skills,
    tasks,
    tools,
)
from app.core.config import settings
from app.core.observability import setup_logging
from app.middleware.api_security_mw import ApiSecurityMiddleware
from app.tools.mcp_manager import mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.checkpoint import checkpoint_provider
    from app.core.startup import phase1_fast, phase2_background
    from app.services.gateway.manager import channel_manager

    setup_logging()

    # Phase 1: fast ready (also registers channels + starts queue consumers)
    await phase1_fast(app)
    from app.services.agent_idle import agent_idle_eviction_service

    agent_idle_eviction_service.start()
    # Phase 2: background heavy init (non-blocking)
    task = asyncio.create_task(phase2_background(app))

    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        from app.services.cron_service import cron_service
        from app.services.run_registry import run_registry

        await agent_idle_eviction_service.stop()
        cron_service.shutdown()
        await run_registry.shutdown()
        await channel_manager.stop()
        await mcp_manager.disconnect()
        try:
            await checkpoint_provider.close()
        except Exception as exc:  # noqa: BLE001
            from app.core.observability import get_logger

            get_logger("startup").error("checkpoint_close_failed", error=str(exc))


app = FastAPI(
    title="BoetClaw DeepAgents",
    description="钻井行业 DeepAgents 智能体系统 - 自主规划与执行",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiSecurityMiddleware)

API_PREFIX = "/api/v1"
app.include_router(agent.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(cron.router, prefix=API_PREFIX)
app.include_router(tasks.router, prefix=API_PREFIX)
app.include_router(domain.router, prefix=API_PREFIX)
app.include_router(tools.router, prefix=API_PREFIX)
app.include_router(gateway.router, prefix=API_PREFIX)
app.include_router(monitor.router, prefix=API_PREFIX)
app.include_router(files.router, prefix=API_PREFIX)
app.include_router(security.router, prefix=API_PREFIX)
app.include_router(skills.router, prefix=API_PREFIX)
app.include_router(agents.router, prefix=API_PREFIX)
app.include_router(providers.router, prefix=API_PREFIX)
app.include_router(plugins.router, prefix=API_PREFIX)
app.include_router(plugins.commands_router, prefix=API_PREFIX)

from app.core.otel import setup_otel

setup_otel(app)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend_dist"
if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")


@app.get("/")
async def root():
    return {
        "name": "BoetClaw DeepAgents",
        "version": "0.1.0",
        "docs": "/docs",
        "api": API_PREFIX,
        "ui": "/ui/",
    }
