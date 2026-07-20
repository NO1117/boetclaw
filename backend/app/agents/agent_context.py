"""Agent routing: 4-level priority resolution."""

from __future__ import annotations

from typing import Any

from app.core.config import settings


def resolve_agent_id(
    *,
    explicit: str | None = None,
    request: Any = None,
    header: str | None = None,
) -> str:
    """Resolve the target agent id.

    Priority: explicit arg > request.state.agent_id > X-Agent-Id header > config default.
    """
    if explicit:
        return explicit
    if request is not None:
        state_val = getattr(getattr(request, "state", None), "agent_id", None)
        if state_val:
            return state_val
    if header:
        return header
    return settings.default_agent_id
