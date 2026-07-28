"""Inject knowledge base retrieval into chat content."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.observability import EventType, emit_event
from app.services.attachments.resolver import _format_chunk_citation, _location_label
from app.services.knowledge_base.models import KnowledgeCitation
from app.services.knowledge_base.retrieval import KBRetrievalResult, retrieve_from_knowledge_bases
from app.services.knowledge_base.service import KnowledgeBaseServiceError, kb_service
from app.services.knowledge_base.store import kb_store


@dataclass(frozen=True)
class KBInjectionResult:
    text_block: str
    citations: list[KnowledgeCitation]
    retrieval_trace: dict[str, Any]
    hit: bool


def resolve_knowledge_for_chat(
    *,
    agent_id: str,
    message: str,
    knowledge_base_ids: list[str] | None,
    trace_id: str = "",
    max_chunks: int | None = None,
    max_chars: int | None = None,
    remaining_chunks: int | None = None,
    remaining_chars: int | None = None,
) -> KBInjectionResult:
    try:
        kb_ids = kb_service.resolve_kb_ids_for_chat(agent_id, knowledge_base_ids)
    except KnowledgeBaseServiceError:
        raise

    if not kb_ids:
        return KBInjectionResult(text_block="", citations=[], retrieval_trace={"hit": False, "hits": 0}, hit=False)

    snapshot = kb_service.build_run_snapshot(agent_id, kb_ids)
    kb_names = {}
    for kb_id in kb_ids:
        kb = kb_store.load_kb(agent_id, kb_id)
        if kb:
            kb_names[kb_id] = kb.name

    chunk_budget = remaining_chunks if remaining_chunks is not None else max_chunks
    char_budget = remaining_chars if remaining_chars is not None else max_chars

    result: KBRetrievalResult = retrieve_from_knowledge_bases(
        agent_id,
        kb_ids,
        message,
        snapshot=snapshot,
        max_chunks=chunk_budget,
        max_chars=char_budget,
        kb_names=kb_names,
    )

    if not result.chunks:
        trace = {
            "hit": False,
            "hits": 0,
            "query_tokens": result.query_tokens,
            "knowledge_base_ids": kb_ids,
            "miss_reason": "no_keyword_match" if result.query_tokens else "empty_query",
        }
        if trace_id:
            emit_event(
                EventType.MEMORY_PERSIST,
                {"action": "knowledge_retrieval", **trace},
                trace_id=trace_id,
                run_id="",
            )
        return KBInjectionResult(text_block="", citations=[], retrieval_trace=trace, hit=False)

    lines: list[str] = []
    for item in result.chunks:
        loc = item.chunk.location.model_dump()
        cite = _format_chunk_citation(item.filename, loc, item.chunk.chunk_id)
        lines.append(f"{cite}\n{item.chunk.text}")

    header = "--- 知识库检索 ---"
    footer = "--- 知识库检索结束 ---"
    text_block = f"{header}\n" + "\n\n".join(lines) + f"\n{footer}"

    trace = {
        "hit": True,
        "hits": len(result.chunks),
        "truncated": result.truncated,
        "total_chars": result.total_chars,
        "query_tokens": result.query_tokens,
        "knowledge_base_ids": kb_ids,
        "citations": [
            {
                "knowledge_base_id": c.knowledge_base_id,
                "document_id": c.document_id,
                "chunk_id": c.chunk_id,
                "location": c.location,
                "score": c.score,
            }
            for c in result.citations
        ],
    }

    if trace_id:
        emit_event(
            EventType.MEMORY_PERSIST,
            {"action": "knowledge_retrieval", **trace},
            trace_id=trace_id,
            run_id="",
        )

    return KBInjectionResult(
        text_block=text_block,
        citations=result.citations,
        retrieval_trace=trace,
        hit=True,
    )
