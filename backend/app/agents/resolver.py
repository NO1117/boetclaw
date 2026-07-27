"""Strict agent graph resolution shared by invocation and resume paths."""

from __future__ import annotations

import hashlib
from typing import Any

from app.agents.graph_cache import get_graph_cache
from app.core.config import settings
from app.core.observability import get_logger
from app.providers.capabilities import provider_config_fingerprint
from app.providers.manager import provider_manager

logger = get_logger("agent_resolver")


class AgentResolutionError(ValueError):
    def __init__(self, message: str, status_code: int = 404) -> None:
        super().__init__(message)
        self.status_code = status_code


async def resolve_agent_graph(agent_id: str) -> Any:
    """Resolve an existing Agent without silently creating or falling back."""
    if agent_id == "default":
        from app.core.agent import agent_manager

        if agent_manager._agent is None:
            await agent_manager.initialize()
        return agent_manager.agent

    from app.agents.multi_agent_manager import multi_agent_manager

    if not multi_agent_manager.is_registered(agent_id):
        raise AgentResolutionError(f"Agent 不存在或已删除：{agent_id}", 404)
    workspace = await multi_agent_manager.get_agent(agent_id)
    return workspace.agent


def _skills_fingerprint(agent_id: str) -> str:
    profile_revision = "0"
    try:
        from app.agents.profile.service import profile_service

        profile_revision = str(profile_service.get_or_create(agent_id).revision)
    except Exception:  # noqa: BLE001
        pass
    if agent_id == "default":
        skills_path = settings.skills_dir
        if skills_path.exists():
            names = sorted(p.name for p in skills_path.iterdir() if p.is_dir())
            base = hashlib.sha256("|".join(names).encode()).hexdigest()[:16]
        else:
            base = "default-skills"
        return f"{base}|p{profile_revision}"
    from app.agents.multi_agent_manager import multi_agent_manager

    root = multi_agent_manager._root / agent_id
    if root.is_dir():
        names = sorted(p.name for p in root.iterdir() if p.is_dir())
        base = hashlib.sha256("|".join(names).encode()).hexdigest()[:16]
        return f"{base}|p{profile_revision}"
    return f"agent-{agent_id}|p{profile_revision}"


async def _checkpoint_identity(agent_id: str) -> str:
    from app.core.checkpoint import checkpoint_provider

    backend = settings.checkpoint_backend
    if backend == "sqlite":
        db_path = checkpoint_provider.database_path(agent_id)
        return f"sqlite:{db_path.stat().st_mtime_ns if db_path.exists() else 0}"
    return f"{backend}:{agent_id}"


async def _build_isolated_graph(agent_id: str, model_string: str) -> Any:
    provider_name, model = provider_manager.parse_model_string(model_string)
    override_model = provider_manager.get_chat_model(model_string)

    if agent_id == "default":
        from app.core.agent_factory import BoetClawAgentFactory, setup_env
        from app.core.checkpoint import checkpoint_provider

        setup_env()
        checkpointer = await checkpoint_provider.get(settings.default_agent_id)
        memory_files = [str(settings.agents_md)] if settings.agents_md.exists() else None
        skills_path = [str(settings.skills_dir)] if settings.skills_dir.exists() else None
        return BoetClawAgentFactory.build(
            model=override_model,
            memory=memory_files,
            skills=skills_path,
            checkpointer=checkpointer,
        )

    from app.agents.multi_agent_manager import multi_agent_manager

    if not multi_agent_manager.is_registered(agent_id):
        raise AgentResolutionError(f"Agent 不存在或已删除：{agent_id}", 404)
    workspace = await multi_agent_manager.get_agent(agent_id)
    return multi_agent_manager.build_agent_with_model(workspace, override_model)


async def build_agent_graph_with_model(agent_id: str, model_string: str) -> tuple[Any, bool, float | None]:
    """Build or retrieve cached isolated per-request graph.

    Returns (agent, cache_hit, build_ms).
    """
    provider_name, model = provider_manager.parse_model_string(model_string)
    skills_fp = _skills_fingerprint(agent_id)
    checkpoint_id = await _checkpoint_identity(agent_id)
    cache = get_graph_cache()
    key = cache.make_key(
        agent_id=agent_id,
        provider=provider_name,
        model=model,
        skills_fingerprint=skills_fp,
        checkpoint_identity=checkpoint_id,
    )
    cache.register_key_meta(key, agent_id=agent_id, provider=provider_name)

    async def builder() -> Any:
        return await _build_isolated_graph(agent_id, model_string)

    agent, hit, build_ms = await cache.get_or_build(key, builder)
    logger.debug(
        "isolated_graph_resolved",
        agent_id=agent_id,
        model=model_string,
        cache_hit=hit,
        provider_fp=provider_config_fingerprint(provider_name)[:8],
    )
    return agent, hit, build_ms
