"""Bounded LRU + TTL cache for isolated per-request agent graphs."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from app.core.config import settings
from app.core.observability import get_logger
from app.providers.capabilities import provider_config_fingerprint

logger = get_logger("graph_cache")


@dataclass
class GraphCacheStats:
    hits: int = 0
    misses: int = 0
    builds: int = 0
    evictions: int = 0
    inflight_waits: int = 0
    current_size: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "builds": self.builds,
            "evictions": self.evictions,
            "inflight_waits": self.inflight_waits,
            "current_size": self.current_size,
        }


@dataclass
class _CacheEntry:
    agent: Any
    created_at: float
    build_ms: float = 0.0


class AgentGraphCache:
    """Thread-safe async graph cache with single-flight builds."""

    def __init__(
        self,
        *,
        max_size: int | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self._max_size = max_size if max_size is not None else settings.graph_cache_max_size
        self._ttl = ttl_seconds if ttl_seconds is not None else float(settings.graph_cache_ttl_seconds)
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()
        self._stats = GraphCacheStats()
        self._last_build_ms: float | None = None

    @property
    def stats(self) -> GraphCacheStats:
        self._stats.current_size = len(self._entries)
        return self._stats

    @property
    def last_build_ms(self) -> float | None:
        return self._last_build_ms

    def make_key(
        self,
        *,
        agent_id: str,
        provider: str,
        model: str,
        skills_fingerprint: str,
        checkpoint_identity: str,
    ) -> str:
        provider_fp = provider_config_fingerprint(provider)
        raw = f"{agent_id}|{provider}|{model}|{skills_fingerprint}|{checkpoint_identity}|{provider_fp}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get_or_build(
        self,
        key: str,
        builder: Callable[[], Coroutine[Any, Any, Any]],
    ) -> tuple[Any, bool, float | None]:
        """Return (agent, cache_hit, build_ms)."""
        now = time.monotonic()
        wait_fut: asyncio.Future[Any] | None = None
        build_fut: asyncio.Future[Any] | None = None

        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None and (now - entry.created_at) <= self._ttl:
                self._entries.move_to_end(key)
                self._stats.hits += 1
                return entry.agent, True, entry.build_ms

            if entry is not None:
                del self._entries[key]

            existing = self._inflight.get(key)
            if existing is not None:
                self._stats.inflight_waits += 1
                wait_fut = existing
            else:
                build_fut = asyncio.get_running_loop().create_future()
                self._inflight[key] = build_fut

        if wait_fut is not None:
            agent = await wait_fut
            return agent, True, None

        assert build_fut is not None
        self._stats.misses += 1
        started = time.monotonic()
        try:
            agent = await builder()
        except Exception as exc:
            async with self._lock:
                inflight = self._inflight.pop(key, None)
                if inflight is build_fut and not build_fut.done():
                    build_fut.set_exception(exc)
            raise

        build_ms = (time.monotonic() - started) * 1000
        self._last_build_ms = build_ms
        async with self._lock:
            inflight = self._inflight.pop(key, None)
            if inflight is build_fut and not build_fut.done():
                build_fut.set_result(agent)

            while len(self._entries) >= self._max_size:
                evicted_key, _ = self._entries.popitem(last=False)
                meta_map = getattr(self, "_key_meta", {})
                meta_map.pop(evicted_key, None)
                self._stats.evictions += 1

            self._entries[key] = _CacheEntry(agent=agent, created_at=time.monotonic(), build_ms=build_ms)
            self._stats.builds += 1
            self._stats.current_size = len(self._entries)

        logger.info("graph_cache_built", key=key[:12], build_ms=round(build_ms, 2))
        return agent, False, build_ms

    def invalidate_agent(self, agent_id: str) -> int:
        meta_map: dict[str, dict[str, str]] = getattr(self, "_key_meta", {})
        to_delete = [k for k, m in meta_map.items() if m.get("agent_id") == agent_id]
        for key in to_delete:
            self._entries.pop(key, None)
            meta_map.pop(key, None)
        if to_delete:
            logger.info("graph_cache_invalidate_agent", agent_id=agent_id, removed=len(to_delete))
        return len(to_delete)

    def invalidate_all(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        self._stats.current_size = 0
        logger.info("graph_cache_invalidate_all", removed=count)
        return count

    def invalidate_provider(self, provider: str) -> int:
        meta_map: dict[str, dict[str, str]] = getattr(self, "_key_meta", {})
        to_delete = [k for k, m in meta_map.items() if m.get("provider") == provider]
        for key in to_delete:
            self._entries.pop(key, None)
            meta_map.pop(key, None)
        if to_delete:
            logger.info("graph_cache_invalidate_provider", provider=provider, removed=len(to_delete))
        return len(to_delete)

    def invalidate_connection(self, connection_id: str) -> int:
        meta_map: dict[str, dict[str, str]] = getattr(self, "_key_meta", {})
        to_delete = [k for k, m in meta_map.items() if m.get("connection_id") == connection_id]
        for key in to_delete:
            self._entries.pop(key, None)
            meta_map.pop(key, None)
        if to_delete:
            logger.info("graph_cache_invalidate_connection", connection_id=connection_id, removed=len(to_delete))
        return len(to_delete)

    def register_key_meta(self, key: str, *, agent_id: str, provider: str, connection_id: str = "") -> None:
        if not hasattr(self, "_key_meta"):
            self._key_meta: dict[str, dict[str, str]] = {}
        meta: dict[str, str] = {"agent_id": agent_id, "provider": provider}
        if connection_id:
            meta["connection_id"] = connection_id
        self._key_meta[key] = meta

    def purge_expired(self) -> int:
        now = time.monotonic()
        expired = [k for k, e in self._entries.items() if (now - e.created_at) > self._ttl]
        for key in expired:
            del self._entries[key]
        if expired:
            self._stats.evictions += len(expired)
        return len(expired)


_graph_cache: AgentGraphCache | None = None


def get_graph_cache() -> AgentGraphCache:
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = AgentGraphCache()
    return _graph_cache
