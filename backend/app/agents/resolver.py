"""Strict agent graph resolution shared by invocation and resume paths."""

from __future__ import annotations

from typing import Any


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


async def build_agent_graph_with_model(agent_id: str, model_string: str) -> Any:
    """Build an isolated per-request graph with the requested model.

    Reuses the workspace/default factory path (tools, skills, checkpointing,
    middleware) without mutating global settings or cached default graphs.
    """
    from app.providers.manager import provider_manager

    override_model = provider_manager.get_chat_model(model_string)

    if agent_id == "default":
        from app.core.agent_factory import BoetClawAgentFactory, setup_env
        from app.core.checkpoint import checkpoint_provider
        from app.core.config import settings

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
