"""Explicit remember/forget intent parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

_REMEMBER_PATTERNS = [
    re.compile(r"(?:请|帮我)?记住[：:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:请|帮我)?记下[：:\s]+(.+)", re.IGNORECASE),
]
_FORGET_PATTERNS = [
    re.compile(r"(?:请|帮我)?(?:忘记|忘掉|删除记忆)[：:\s]+(.+)", re.IGNORECASE),
    re.compile(r"不要再记住[：:\s]+(.+)", re.IGNORECASE),
]


@dataclass(frozen=True)
class MemoryIntent:
    kind: str  # remember | forget
    content: str


def parse_memory_intent(message: str) -> MemoryIntent | None:
    text = (message or "").strip()
    if not text:
        return None
    for pattern in _REMEMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            content = match.group(1).strip()
            if content:
                return MemoryIntent(kind="remember", content=content)
    for pattern in _FORGET_PATTERNS:
        match = pattern.search(text)
        if match:
            content = match.group(1).strip()
            if content:
                return MemoryIntent(kind="forget", content=content)
    return None
