"""Minimal shared request preparation for synchronous and SSE chat."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from pydantic import ValidationError

from app.agents.resolver import resolve_agent_graph
from app.commands.registry import CommandResult, command_registry
from app.core.config import settings
from app.core.observability import new_run_id, new_trace_id
from app.i18n import lang_from_headers
from app.memory.context_policy import normalize_source
from app.providers.compatibility import (
    ModelCompatibilityError,
    check_model_compatibility,
    derive_input_requirements,
)
from app.providers.manager import provider_manager
from app.providers.rate_limiter import ProviderRateLimitError
from app.services.chat_attachments import (
    AttachmentSummary,
    AttachmentValidationError,
    ChatAttachmentInput,
    prepare_attachment_content,
)
from app.services.attachments.resolver import ResolvedAttachmentContent, resolve_attachment_ids_for_chat
from app.services.run_registry import run_registry


class ChatPreparationError(ValueError):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        *,
        error_code: str | None = None,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail or {}


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
    user_content: str | list[Any]
    history_user_message: str
    attachment_summaries: list[AttachmentSummary]
    attachment_refs: list[dict[str, Any]]
    retrieval_hits: int = 0
    provider_override: str | None = None
    model_override: str | None = None
    model_string: str | None = None
    command: CommandResult | None = None
    memory_context: dict | None = None
    memory_candidates: list[dict] = field(default_factory=list)
    memory_actions: list[dict] = field(default_factory=list)

    @property
    def response_thread_id(self) -> str:
        if self.command and self.command.new_thread_id:
            return self.command.new_thread_id
        return self.thread_id


def _resolve_model_override(provider: str | None, model: str | None) -> tuple[str | None, str | None, str | None]:
    if not provider and not model:
        return None, None, None
    if not provider or not model:
        raise ChatPreparationError("provider 与 model 必须同时提供")
    provider_name = provider.strip()
    model_name = model.strip()
    if not provider_name or not model_name:
        raise ChatPreparationError("provider 与 model 不能为空")
    try:
        provider_manager.get(provider_name)
    except ValueError as exc:
        raise ChatPreparationError(str(exc)) from exc
    known = {m.name for m in provider_manager.list_models(provider_name)}
    if model_name not in known:
        raise ChatPreparationError(f"未知模型: {provider_name}/{model_name}")
    model_string = f"{provider_name}:{model_name}"
    try:
        provider_manager.get_chat_model(model_string)
    except ProviderRateLimitError as exc:
        raise ChatPreparationError(str(exc), 429) from exc
    return provider_name, model_name, model_string


def _assert_model_compatibility(
    provider: str,
    model: str,
    *,
    has_images: bool,
    image_count: int,
    attachment_count: int,
    document_count: int,
) -> None:
    requirements = derive_input_requirements(
        has_images=has_images,
        image_count=image_count,
        attachment_count=attachment_count,
        document_count=document_count,
    )
    result = check_model_compatibility(provider, model, requirements)
    if result.status == "incompatible":
        raise ModelCompatibilityError(
            result.reason,
            missing_capabilities=result.missing_capabilities,
            provider=provider,
            model=model,
        )


async def prepare_chat(
    *,
    message: str,
    attachments: list[dict[str, Any]] | None,
    attachment_ids: list[str] | None = None,
    thread_id: str | None,
    agent_id: str | None,
    source: str | None,
    lang: str | None,
    headers: Mapping[str, str] | None,
    provider: str | None = None,
    model: str | None = None,
) -> PreparedChat:
    """Normalize request metadata, resolve the graph, and intercept slash commands."""
    resolved_thread_id = thread_id or uuid.uuid4().hex[:16]
    resolved_agent_id = agent_id or "default"
    resolved_lang = lang_from_headers(dict(headers or {}), lang)
    resolved_source = normalize_source(source)
    provider_override, model_override, model_string = _resolve_model_override(provider, model)
    trace_id = new_trace_id()

    attachment_inputs: list[ChatAttachmentInput] = []
    for item in attachments or []:
        try:
            attachment_inputs.append(ChatAttachmentInput.model_validate(item))
        except ValidationError as exc:
            raise ChatPreparationError("附件字段无效") from exc

    try:
        if attachment_ids:
            resolved = await resolve_attachment_ids_for_chat(
                message=message,
                agent_id=resolved_agent_id,
                attachment_ids=attachment_ids,
                inline_attachments=None,
                trace_id=trace_id,
            )
        elif attachment_inputs:
            prepared = prepare_attachment_content(message, attachment_inputs)
            resolved = ResolvedAttachmentContent(
                user_content=prepared.user_content,
                history_text=prepared.history_text,
                summaries=prepared.summaries,
                has_images=prepared.has_images,
                attachment_refs=[],
                retrieval_trace={},
            )
        else:
            text = message.strip()
            if not text:
                raise ChatPreparationError("消息与附件均为空")
            resolved = ResolvedAttachmentContent(
                user_content=text,
                history_text=text,
                summaries=[],
                has_images=False,
                attachment_refs=[],
                retrieval_trace={},
            )
    except AttachmentValidationError as exc:
        raise ChatPreparationError(str(exc), exc.status_code) from exc

    image_count = sum(1 for s in resolved.summaries if getattr(s, "kind", "") == "image")
    if not image_count and resolved.has_images:
        image_count = 1
    document_count = sum(1 for s in resolved.summaries if getattr(s, "kind", "") in {"text", "document"})
    attachment_count = len(resolved.summaries) or len(attachment_ids or []) or len(attachment_inputs)
    retrieval_hits = int((resolved.retrieval_trace or {}).get("hits", 0) or 0)

    effective_provider = provider_override
    effective_model = model_override
    if not effective_provider:
        effective_provider, effective_model = provider_manager.parse_model_string(settings.model_string)

    try:
        _assert_model_compatibility(
            effective_provider,
            effective_model,
            has_images=resolved.has_images,
            image_count=image_count,
            attachment_count=attachment_count,
            document_count=document_count,
        )
    except ModelCompatibilityError as exc:
        raise ChatPreparationError(
            str(exc),
            exc.status_code,
            error_code=exc.error_code,
            detail=exc.to_detail(),
        ) from exc

    command_message = message.strip() or message
    command = command_registry.execute(
        command_message,
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

    memory_context: dict | None = None
    memory_candidates: list[dict] = []
    memory_actions: list[dict] = []
    effective_user_content = resolved.user_content
    if agent is not None and command is None:
        from app.memory.service import memory_service

        effective_user_content, summary, actions, candidates = memory_service.prepare_chat_memory(
            agent_id=resolved_agent_id,
            thread_id=resolved_thread_id,
            message=message,
            source=resolved_source,
            trace_id=trace_id,
            user_content=resolved.user_content,
        )
        memory_context = summary.model_dump()
        memory_candidates = [item.model_dump() for item in candidates]
        memory_actions = [item.model_dump() for item in actions]

    return PreparedChat(
        message=message,
        thread_id=resolved_thread_id,
        agent_id=resolved_agent_id,
        source=resolved_source,
        lang=resolved_lang,
        trace_id=trace_id,
        run_id=new_run_id(),
        agent=agent,
        user_content=effective_user_content,
        history_user_message=resolved.history_text,
        attachment_summaries=resolved.summaries,
        attachment_refs=list(resolved.attachment_refs),
        retrieval_hits=retrieval_hits,
        provider_override=provider_override,
        model_override=model_override,
        model_string=model_string,
        command=command,
        memory_context=memory_context,
        memory_candidates=memory_candidates,
        memory_actions=memory_actions,
    )
