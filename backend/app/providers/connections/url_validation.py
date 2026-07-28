"""Validate provider base URLs."""

from __future__ import annotations

from urllib.parse import urlparse


class UrlValidationError(ValueError):
    pass


def validate_base_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise UrlValidationError("Base URL 仅允许 http 或 https 协议")
    if parsed.username or parsed.password:
        raise UrlValidationError("Base URL 不得包含用户名或密码")
    if ".." in parsed.path:
        raise UrlValidationError("Base URL 路径无效")
    # Normalize: strip trailing slash except root
    normalized = cleaned.rstrip("/")
    return normalized
