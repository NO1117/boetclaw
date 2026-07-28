"""Voice request rate limiting and concurrency guard."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.providers.speech.errors import VOICE_RATE_LIMITED, VoiceError


class VoiceRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._semaphore = asyncio.Semaphore(max(1, settings.speech_max_concurrent))

    def reset(self) -> None:
        self._hits.clear()

    def check(self, key: str) -> None:
        limit = settings.speech_rate_limit_per_minute
        if limit <= 0:
            return
        now = time.monotonic()
        window_start = now - 60
        hits = self._hits[key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= limit:
            raise VoiceError(VOICE_RATE_LIMITED, "语音请求过于频繁", status_code=429)
        hits.append(now)

    async def acquire(self) -> None:
        await self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()


voice_rate_limiter = VoiceRateLimiter()
