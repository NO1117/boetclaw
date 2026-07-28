"""Shared document parse and index pipeline for attachments and knowledge base."""

from __future__ import annotations

from app.core.config import settings
from app.core.observability import get_logger
from app.services.attachments.chunking import build_keyword_index
from app.services.attachments.models import DocumentSummary, TextChunk
from app.services.attachments.parsers import parser_registry
from app.services.attachments.security import infer_kind

logger = get_logger("parse_pipeline")


class ParsePipelineError(RuntimeError):
    pass


def safe_error_summary(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "解析失败"
    if any(token in message.lower() for token in ("\\", "/", "traceback", "line ")):
        return "解析失败"
    return message[:240]


def parse_document_bytes(
    *,
    data: bytes,
    filename: str,
    mime_type: str,
    content_id: str,
) -> tuple[list[TextChunk], DocumentSummary, str]:
    """Parse bytes into chunks and summary. Returns (chunks, summary, kind)."""
    kind = infer_kind(mime_type, filename)

    if kind == "image":
        summary = DocumentSummary(searchable=False)
        return [], summary, kind

    if kind == "binary":
        summary = DocumentSummary(searchable=False)
        return [], summary, kind

    parser = parser_registry.get(mime_type, filename)
    if parser is None:
        raise ParsePipelineError(f"暂不支持解析此格式: {mime_type}")

    result = parser.parse(data, attachment_id=content_id, filename=filename)
    if len(result.plain_text) > settings.attachment_max_parse_chars:
        raise ParsePipelineError("文档文本超过解析上限")

    return result.chunks, result.summary, kind


def build_index_for_chunks(chunks: list[TextChunk]) -> dict[str, list[str]]:
    return build_keyword_index(chunks)
