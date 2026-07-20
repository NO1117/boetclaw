"""Lightweight in-memory provider rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import settings


class ProviderRateLimitError(RuntimeError):
    """Raised when provider model resolution exceeds the configured limit."""


class ProviderRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._hits.clear()

    def check(self, provider: str, model: str) -> None:
        limit = settings.provider_rate_limit_per_minute
        if limit <= 0:
            return
        key = f"{provider}:{model}"
        now = time.monotonic()
        window_start = now - 60
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= limit:
            raise ProviderRateLimitError(f"Provider rate limit exceeded for {key}")
        hits.append(now)


provider_rate_limiter = ProviderRateLimiter()
