"""Per-run context shared with tools."""

from __future__ import annotations

import json
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import run_id_var, trace_id_var

task_id_var: ContextVar[str] = ContextVar("task_id", default="")
agent_id_var: ContextVar[str] = ContextVar("agent_id", default="default")
thread_id_var: ContextVar[str] = ContextVar("thread_id", default="")
well_id_var: ContextVar[str] = ContextVar("well_id", default="")


def set_run_context(
    *,
    task_id: str = "",
    agent_id: str = "default",
    thread_id: str = "",
    well_id: str = "",
) -> list[tuple[ContextVar[str], Token[str]]]:
    return [
        (task_id_var, task_id_var.set(task_id)),
        (agent_id_var, agent_id_var.set(agent_id or "default")),
        (thread_id_var, thread_id_var.set(thread_id)),
        (well_id_var, well_id_var.set(well_id)),
    ]


def reset_run_context(tokens: list[tuple[ContextVar[str], Token[str]]]) -> None:
    for var, token in reversed(tokens):
        var.reset(token)


def write_artifact_meta(kind: str, filename: str, *, well_id: str = "", extra: dict[str, Any] | None = None) -> Path:
    artifacts_dir = settings.workspace_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id_var.get(),
        "trace_id": trace_id_var.get(),
        "run_id": run_id_var.get(),
        "agent_id": agent_id_var.get(),
        "thread_id": thread_id_var.get(),
        "well_id": well_id or well_id_var.get(),
    }
    if extra:
        meta.update({k: v for k, v in extra.items() if v not in (None, "")})
    meta_path = artifacts_dir / f"{kind}_{filename}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path
