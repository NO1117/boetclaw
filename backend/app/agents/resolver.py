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
