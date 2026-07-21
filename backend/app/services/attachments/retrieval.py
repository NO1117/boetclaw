"""Local keyword retrieval over attachment chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.attachments.models import TextChunk
from app.services.attachments.store import attachment_store

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: TextChunk
    score: float
    attachment_id: str


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    truncated: bool
    total_chars: int
    query_tokens: list[str]


def _query_tokens(query: str) -> list[str]:
    tokens = [t.lower() for t in _WORD_RE.findall(query) if len(t) >= 2]
    return tokens[:32]


def retrieve_for_query(
    agent_id: str,
    attachment_ids: list[str],
    query: str,
    *,
    max_chunks: int | None = None,
    max_chars: int | None = None,
) -> RetrievalResult:
    chunk_limit = max_chunks or settings.attachment_retrieval_max_chunks
    char_limit = max_chars or settings.attachment_retrieval_max_chars
    tokens = _query_tokens(query or "")
    scored: dict[str, RetrievedChunk] = {}

    for attachment_id in attachment_ids:
        chunks = attachment_store.load_chunks(agent_id, attachment_id)
        index = attachment_store.load_keyword_index(agent_id, attachment_id)
        if tokens and index:
            for token in tokens:
                for chunk_id in index.get(token, []):
                    chunk = next((c for c in chunks if c.chunk_id == chunk_id), None)
                    if chunk is None:
                        continue
                    existing = scored.get(chunk_id)
                    score = (existing.score if existing else 0) + 1.0
                    scored[chunk_id] = RetrievedChunk(chunk=chunk, score=score, attachment_id=attachment_id)
        elif not tokens:
            for chunk in chunks[:chunk_limit]:
                scored[chunk.chunk_id] = RetrievedChunk(chunk=chunk, score=0.0, attachment_id=attachment_id)

    ranked = sorted(scored.values(), key=lambda item: (-item.score, item.chunk.order))
    selected: list[RetrievedChunk] = []
    total_chars = 0
    truncated = False
    for item in ranked:
        if len(selected) >= chunk_limit:
            truncated = True
            break
        if total_chars + len(item.chunk.text) > char_limit:
            truncated = True
            break
        selected.append(item)
        total_chars += len(item.chunk.text)
    return RetrievalResult(chunks=selected, truncated=truncated, total_chars=total_chars, query_tokens=tokens)
