"""Heuristic candidate extraction from user chat."""

from __future__ import annotations

import re

_CANDIDATE_HINTS = [
    re.compile(r"我(?:的)?(?:偏好|习惯|默认|喜欢|常用)是"),
    re.compile(r"以后请"),
    re.compile(r"请记住我"),
    re.compile(r"长期目标"),
    re.compile(r"不要(?:再)?"),
    re.compile(r"我(?:是|在|负责)"),
]
_QUESTION_ONLY = re.compile(r"^[？?].*[？?]$|^(?:什么|怎么|如何|为什么|哪|谁|多少)")


def should_extract_candidate(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) < 8:
        return False
    if _QUESTION_ONLY.search(text):
        return False
    if text.endswith("?") or text.endswith("？"):
        return False
    return any(pattern.search(text) for pattern in _CANDIDATE_HINTS)


def summarize_content(content: str, *, max_len: int = 120) -> str:
    text = " ".join(content.strip().split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
