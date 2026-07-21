"""Sensitive content detection for memory writes."""

from __future__ import annotations

import re

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token)\b"),
    re.compile(r"(?i)\b(bearer\s+[a-z0-9\-._~+/]+=*)\b"),
    re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(cookie)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(mongodb(\+srv)?|postgres(ql)?|mysql|redis)://[^\s]+"),
    re.compile(r"(?i)\b(sk-[a-z0-9]{20,}|xox[baprs]-[a-z0-9-]{10,})\b"),
    re.compile(r"(?i)\b(AKIA[0-9A-Z]{16})\b"),
]


def contains_sensitive_content(text: str) -> bool:
    if not text or not text.strip():
        return False
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def reject_reason(text: str) -> str:
    if contains_sensitive_content(text):
        return "检测到疑似凭据或密钥，已拒绝保存"
    return ""
