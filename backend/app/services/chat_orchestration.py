"""Minimal shared request preparation for synchronous and SSE chat."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from app.agents.resolver import resolve_agent_graph
from app.commands.registry import CommandResult, command_registry
from app.core.observability import new_run_id, new_trace_id
from app.i18n import lang_from_headers
from app.memory.context_policy import normalize_source
from app.services.run_registry import run_registry


@dataclass(frozen=True)
class PreparedChat:
    message: str
    thread_id: str
    agent_id: str
    source: str
    lang: str
    trace_id: str
    run_id: str
    agent: Any | None
    command: CommandResult | None = None

    @property
    def response_thread_id(self) -> str:
        if self.command and self.command.new_thread_id:
            return self.command.new_thread_id
        return self.thread_id


async def prepare_chat(
    *,
    message: str,
    thread_id: str | None,
    agent_id: str | None,
    source: str | None,
    lang: str | None,
    headers: Mapping[str, str] | None,
) -> PreparedChat:
    """Normalize request metadata, resolve the graph, and intercept slash commands."""
    resolved_thread_id = thread_id or uuid.uuid4().hex[:16]
    resolved_agent_id = agent_id or "default"
    resolved_lang = lang_from_headers(dict(headers or {}), lang)
    resolved_source = normalize_source(source)
    command = command_registry.execute(
        message,
        {
            "thread_id": resolved_thread_id,
            "agent_id": resolved_agent_id,
            "source": resolved_source,
            "lang": resolved_lang,
        },
    )
    if command is not None and (not command.handled or command.pass_through):
        command = None
    if command is not None and command.action == "stop":
        from app.i18n import t

        cancelled = await run_registry.cancel(
            agent_id=resolved_agent_id,
            thread_id=resolved_thread_id,
        )
        command.response = t(
            "commands.stop.cancelled" if cancelled.cancelled else "commands.stop.no_run",
            resolved_lang,
        )
    agent = None if command is not None else await resolve_agent_graph(resolved_agent_id)
    return PreparedChat(
        message=message,
        thread_id=resolved_thread_id,
        agent_id=resolved_agent_id,
        source=resolved_source,
        lang=resolved_lang,
        trace_id=new_trace_id(),
        run_id=new_run_id(),
        agent=agent,
        command=command,
    )
