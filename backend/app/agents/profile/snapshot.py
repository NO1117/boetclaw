"""Runtime configuration snapshots for in-flight runs."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from app.agents.profile.models import EffectiveAgentConfig

_profile_snapshot_var: ContextVar[dict[str, Any] | None] = ContextVar("agent_profile_snapshot", default=None)


def capture_snapshot(effective: EffectiveAgentConfig) -> dict[str, Any]:
    return effective.model_dump()


def set_run_snapshot(snapshot: dict[str, Any]) -> Token:
    return _profile_snapshot_var.set(snapshot)


def get_run_snapshot() -> dict[str, Any] | None:
    return _profile_snapshot_var.get()


def reset_run_snapshot(token: Token) -> None:
    _profile_snapshot_var.reset(token)
