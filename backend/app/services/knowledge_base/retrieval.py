"""Knowledge base keyword retrieval — no full-corpus fallback on miss."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.attachments.models import TextChunk
from app.services.knowledge_base.models import KnowledgeCitation
from app.services.knowledge_base.store import kb_store

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class KBRetrievedChunk:
    chunk: TextChunk
    score: float
    document_id: str
    knowledge_base_id: str
    sha256: str
    filename: str


@dataclass(frozen=True)
class KBRetrievalResult:
    chunks: list[KBRetrievedChunk]
    citations: list[KnowledgeCitation]
    truncated: bool
    total_chars: int
    query_tokens: list[str]
    hit: bool


def _query_tokens(query: str) -> list[str]:
    tokens = [t.lower() for t in _WORD_RE.findall(query or "") if len(t) >= 2]
    return tokens[:32]


def retrieve_from_knowledge_bases(
    agent_id: str,
    kb_ids: list[str],
    query: str,
    *,
    snapshot: dict[str, str] | None = None,
    max_chunks: int | None = None,
    max_chars: int | None = None,
    kb_names: dict[str, str] | None = None,
) -> KBRetrievalResult:
    chunk_limit = max_chunks or settings.attachment_retrieval_max_chunks
    char_limit = max_chars or settings.attachment_retrieval_max_chars
    tokens = _query_tokens(query or "")

    if not kb_ids:
        return KBRetrievalResult(
            chunks=[],
            citations=[],
            truncated=False,
            total_chars=0,
            query_tokens=tokens,
            hit=False,
        )

    scored: dict[str, KBRetrievedChunk] = {}
    names = kb_names or {}

    for kb_id in kb_ids:
        kb = kb_store.load_kb(agent_id, kb_id)
        if kb is None or kb.status != "active":
            continue
        kb_name = names.get(kb_id) or kb.name
        for doc in kb_store.list_documents(agent_id, kb_id):
            if doc.status != "ready":
                continue
            if snapshot is not None and doc.document_id not in snapshot:
                continue
            if snapshot is not None and snapshot.get(doc.document_id) != doc.updated_at:
                continue

            chunks = kb_store.load_blob_chunks(agent_id, doc.sha256)
            index = kb_store.load_blob_index(agent_id, doc.sha256)

            if tokens and index:
                for token in tokens:
                    for chunk_id in index.get(token, []):
                        chunk = next((c for c in chunks if c.chunk_id == chunk_id), None)
                        if chunk is None:
                            continue
                        key = f"{doc.document_id}:{chunk_id}"
                        existing = scored.get(key)
                        score = (existing.score if existing else 0) + 1.0
                        scored[key] = KBRetrievedChunk(
                            chunk=chunk,
                            score=score,
                            document_id=doc.document_id,
                            knowledge_base_id=kb_id,
                            sha256=doc.sha256,
                            filename=doc.filename,
                        )

    ranked = sorted(scored.values(), key=lambda item: (-item.score, item.chunk.order))
    selected: list[KBRetrievedChunk] = []
    citations: list[KnowledgeCitation] = []
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
        kb = kb_store.load_kb(agent_id, item.knowledge_base_id)
        kb_name = names.get(item.knowledge_base_id) or (kb.name if kb else "")
        snippet = item.chunk.text[:240]
        citations.append(
            KnowledgeCitation(
                knowledge_base_id=item.knowledge_base_id,
                knowledge_base_name=kb_name,
                document_id=item.document_id,
                document_name=item.filename,
                chunk_id=item.chunk.chunk_id,
                location=item.chunk.location.model_dump(),
                score=item.score,
                truncated=truncated,
                snippet=snippet,
            )
        )

    hit = bool(selected) and bool(tokens)
    return KBRetrievalResult(
        chunks=selected,
        citations=citations,
        truncated=truncated,
        total_chars=total_chars,
        query_tokens=tokens,
        hit=hit,
    )
