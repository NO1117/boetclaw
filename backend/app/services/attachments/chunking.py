"""Structure-aware chunking for parsed attachment text."""

from __future__ import annotations

import re
import uuid

from app.core.config import settings
from app.services.attachments.models import ChunkLocation, TextChunk

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _make_chunk(
    attachment_id: str,
    order: int,
    text: str,
    location: ChunkLocation,
) -> TextChunk:
    return TextChunk(
        chunk_id=f"{attachment_id}-c{order:04d}",
        attachment_id=attachment_id,
        order=order,
        text=text.strip(),
        location=location,
        token_estimate=_estimate_tokens(text),
    )


def chunk_plain_sections(
    attachment_id: str,
    sections: list[tuple[str, ChunkLocation]],
    *,
    max_chars: int | None = None,
) -> list[TextChunk]:
    limit = max_chars or settings.attachment_chunk_max_chars
    chunks: list[TextChunk] = []
    order = 0
    for body, location in sections:
        body = body.strip()
        if not body:
            continue
        start = 0
        while start < len(body):
            end = min(len(body), start + limit)
            if end < len(body):
                split_at = body.rfind("\n\n", start, end)
                if split_at <= start:
                    split_at = body.rfind("\n", start, end)
                if split_at > start:
                    end = split_at
            piece = body[start:end].strip()
            if piece:
                chunks.append(_make_chunk(attachment_id, order, piece, location))
                order += 1
            start = end if end > start else len(body)
            if len(chunks) >= settings.attachment_max_chunks:
                return chunks
    return chunks


def chunk_flat_text(attachment_id: str, text: str) -> list[TextChunk]:
    return chunk_plain_sections(attachment_id, [(text, ChunkLocation())])


def build_keyword_index(chunks: list[TextChunk]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for chunk in chunks:
        for token in set(_WORD_RE.findall(chunk.text.lower())):
            if len(token) < 2:
                continue
            index.setdefault(token, []).append(chunk.chunk_id)
    return index
