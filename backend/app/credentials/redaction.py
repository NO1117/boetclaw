"""Redact secrets from logs, traces, API payloads and error messages."""

from __future__ import annotations

import re
from typing import Any

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(authorization)\s*[:=]\s*\S+", re.I), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[a-z0-9\-._~+/]+=*\b"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(sk-[a-z0-9]{8,})\b"), "sk-[REDACTED]"),
    (re.compile(r"(?i)\b(sk-ant-[a-z0-9\-_]{8,})\b"), "sk-ant-[REDACTED]"),
    (re.compile(r"(?i)\b(xox[baprs]-[a-z0-9-]{10,})\b"), "xox[REDACTED]"),
    (re.compile(r"(?i)\b(AKIA[0-9A-Z]{16})\b"), "AKIA[REDACTED]"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"(?i)(ciphertext|nonce|master[_-]?key)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
]

_SENSITIVE_KEYS = frozenset({
    "api_key",
    "apikey",
    "authorization",
    "ciphertext",
    "nonce",
    "master_key",
    "secret",
    "token",
    "password",
    "credential",
    "credentials",
})


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern, repl in _REDACT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_value(v, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [redact_value(v, depth=depth + 1) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value(v, depth=depth + 1) for v in value)
    return value


def fingerprint_last4(value: str) -> str:
    """Return last 4 chars for safe display; empty if too short."""
    cleaned = value.strip()
    if len(cleaned) < 4:
        return ""
    return cleaned[-4:]
