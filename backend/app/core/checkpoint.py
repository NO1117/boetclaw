"""Application-owned LangGraph checkpointer lifecycle and agent isolation."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from app.core.config import settings


class CheckpointProvider:
    """Own one checkpointer per agent and close persistent connections centrally."""

    def __init__(self, backend: str, sqlite_path: Path) -> None:
        self.backend = backend
        self.sqlite_path = sqlite_path
        self._savers: dict[str, Any] = {}
        self._contexts: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._closed = False
        self._error = ""

    async def initialize(self) -> None:
        """Initialize the configured backend and verify the default saver."""
        self._closed = False
        self._error = ""
        try:
            self._validate_backend()
            if self.backend == "sqlite":
                self.sqlite_path.mkdir(parents=True, exist_ok=True)
            await self.get(settings.default_agent_id)
        except Exception as exc:
            self._error = str(exc)
            raise

    async def get(self, agent_id: str) -> Any:
        if self._closed:
            raise RuntimeError("checkpoint provider 已关闭")
        self._validate_backend()
        if not agent_id:
            raise ValueError("agent_id 不能为空")
        if agent_id in self._savers:
            return self._savers[agent_id]

        lock = self._locks.setdefault(agent_id, asyncio.Lock())
        async with lock:
            if agent_id in self._savers:
                return self._savers[agent_id]
            try:
                saver = await self._open(agent_id)
            except Exception as exc:
                self._error = str(exc)
                raise
            self._savers[agent_id] = saver
            return saver

    def _validate_backend(self) -> None:
        if self.backend not in {"sqlite", "memory"}:
            raise ValueError("CHECKPOINT_BACKEND 必须是 sqlite 或 memory")

    async def _open(self, agent_id: str) -> Any:
        if self.backend == "memory":
            from langgraph.checkpoint.memory import MemorySaver

            return MemorySaver()

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        self.sqlite_path.mkdir(parents=True, exist_ok=True)
        db_path = self.database_path(agent_id)
        context = AsyncSqliteSaver.from_conn_string(str(db_path))
        saver = await context.__aenter__()
        try:
            await saver.setup()
        except Exception:
            await context.__aexit__(None, None, None)
            raise
        self._contexts[agent_id] = context
        return saver

    def database_path(self, agent_id: str) -> Path:
        digest = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:20]
        return self.sqlite_path / f"agent-{digest}.sqlite3"

    async def purge(self, agent_id: str) -> bool:
        """Close and delete persistent checkpoint files for one agent.

        Only removes paths derived from ``database_path`` under ``sqlite_path``.
        """
        if not agent_id:
            raise ValueError("agent_id 不能为空")
        if agent_id == settings.default_agent_id:
            raise ValueError("默认智能体 checkpoint 不可清除")

        context = self._contexts.pop(agent_id, None)
        self._savers.pop(agent_id, None)
        self._locks.pop(agent_id, None)
        if context is not None:
            await context.__aexit__(None, None, None)

        if self.backend != "sqlite":
            return True

        db_path = self.database_path(agent_id)
        root = self.sqlite_path.resolve()
        resolved = db_path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"checkpoint 路径越界：{resolved}") from exc

        removed = False
        for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
            if path.exists():
                path.unlink()
                removed = True
        return removed

    async def close(self) -> None:
        errors: list[str] = []
        for agent_id, context in list(self._contexts.items())[::-1]:
            try:
                await context.__aexit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{agent_id}: {exc}")
        self._contexts.clear()
        self._savers.clear()
        self._locks.clear()
        self._closed = True
        if errors:
            self._error = "; ".join(errors)
            raise RuntimeError(f"关闭 checkpoint provider 失败：{self._error}")

    def status(self) -> dict[str, Any]:
        persistent = self.backend == "sqlite"
        status = "error" if self._error else ("closed" if self._closed else "ready")
        warning = ""
        if self.backend == "memory":
            warning = "memory 模式不支持跨重启恢复"
        elif self.backend != "sqlite":
            warning = "checkpoint backend 配置无效"
        return {
            "status": status,
            "backend": self.backend,
            "persistent": persistent,
            "supports_restart_resume": persistent,
            "warning": warning,
            "sqlite_path": str(self.sqlite_path) if persistent else "",
            "open_agent_savers": len(self._savers),
            "error": self._error,
        }


checkpoint_provider = CheckpointProvider(
    backend=settings.checkpoint_backend,
    sqlite_path=settings.checkpoint_sqlite_path,
)
