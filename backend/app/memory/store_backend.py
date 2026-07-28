"""Memory backend selection: file (AGENTS.md) vs cross-thread store."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.observability import get_logger

logger = get_logger("memory_backend")

_store: Any = None


def get_store() -> Any | None:
    """Return a langgraph Store for cross-thread long-term memory.

    Only instantiated when memory_backend == 'store'. Returns None otherwise so
    callers fall back to file-based memory (AGENTS.md) or SQLite user memory.
    """
    global _store
    if settings.memory_backend not in {"store"}:
        return None
    if _store is None:
        try:
            from langgraph.store.memory import InMemoryStore

            _store = InMemoryStore()
            logger.info("store_backend_initialized", backend="in_memory")
        except Exception as exc:  # noqa: BLE001
            logger.warning("store_backend_init_failed", error=str(exc))
            return None
    return _store


def get_memory_files() -> list[str] | None:
    """File-based memory sources for create_deep_agent(memory=...)."""
    if settings.memory_backend in {"none", "sqlite"}:
        return None
    if settings.memory_backend == "file" or settings.agents_md.exists():
        if settings.agents_md.exists():
            return [str(settings.agents_md)]
    return None
