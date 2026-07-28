"""Sanitize task payloads before persistence and API exposure."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import settings

_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|authorization|bearer\s+[a-z0-9\-_.]+)", re.IGNORECASE),
    re.compile(r"(?i)(password|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
]

_TRUNCATED_SUFFIX = "\n…[truncated]"


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def truncate_text(text: str, max_chars: int | None = None) -> tuple[str, bool]:
    limit = max_chars or settings.task_queue_text_max_chars
    if len(text) <= limit:
        return text, False
    return text[: max(0, limit - len(_TRUNCATED_SUFFIX))] + _TRUNCATED_SUFFIX, True


def sanitize_text(text: str, *, max_chars: int | None = None) -> str:
    cleaned = _redact_text(str(text or ""))
    truncated, _ = truncate_text(cleaned, max_chars)
    return truncated


def sanitize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in snapshot.items():
        lowered = key.lower()
        if any(token in lowered for token in ("key", "secret", "token", "password", "credential")):
            safe[key] = "[REDACTED]"
        elif isinstance(value, str):
            safe[key] = sanitize_text(value, max_chars=512)
        elif isinstance(value, dict):
            safe[key] = sanitize_snapshot(value)
        else:
            safe[key] = value
    return safe


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"kb_content", "knowledge_body", "authorization", "api_key"}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in blocked:
            continue
        if isinstance(value, str):
            safe[key] = sanitize_text(value, max_chars=1024)
        elif isinstance(value, dict):
            safe[key] = sanitize_snapshot(value)
        else:
            safe[key] = value
    return safe
