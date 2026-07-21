"""Multi-agent manager: lazy-loaded, isolated workspaces."""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import get_logger
from app.agents.workspace import Workspace

logger = get_logger("multi_agent")


class MultiAgentManager:
    """Manages multiple isolated agent workspaces with lazy loading."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or settings.agents_root
        self._ws: dict[str, Workspace] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self._locks:
            self._locks[agent_id] = asyncio.Lock()
        return self._locks[agent_id]

    def _deleted_marker(self, agent_id: str) -> Path:
        return self._root / agent_id / ".deleted"

    def _purged_marker(self, agent_id: str) -> Path:
        return self._root / ".purged" / agent_id

    def is_tombstoned(self, agent_id: str) -> bool:
        return self._deleted_marker(agent_id).exists()

    def was_purged(self, agent_id: str) -> bool:
        return self._purged_marker(agent_id).exists()

    def is_registered(self, agent_id: str) -> bool:
        """Return whether an Agent is registered in memory or on disk."""
        if agent_id == settings.default_agent_id:
            return True
        if self.is_tombstoned(agent_id) or self.was_purged(agent_id):
            return False
        return agent_id in self._ws or (self._root / agent_id).is_dir()

    def _ensure_workspace(self, agent_id: str) -> Workspace:
        """Return in-memory workspace metadata without building the graph."""
        ws = self._ws.get(agent_id)
        if ws is not None:
            return ws
        ws = Workspace(agent_id=agent_id, root=self._root / agent_id)
        self._ws[agent_id] = ws
        return ws

    def _discover_disk(self) -> None:
        """Scan agents_root for workspace dirs; skip tombstones; no graph build."""
        if not self._root.is_dir():
            return
        for child in self._root.iterdir():
            if not child.is_dir():
                continue
            agent_id = child.name
            if agent_id.startswith("."):
                continue
            if self.is_tombstoned(agent_id):
                self._ws.pop(agent_id, None)
                continue
            if agent_id not in self._ws:
                self._ws[agent_id] = Workspace(agent_id=agent_id, root=child)

    def _build_agent(self, ws: Workspace, *, model: Any | None = None) -> Any:
        from deepagents.backends import FilesystemBackend

        from app.core.agent_factory import BoetClawAgentFactory, setup_env
        from app.memory.store_backend import get_memory_files, get_store
        from app.skills_system.registry import resolve_effective_skills

        setup_env()
        ws.root.mkdir(parents=True, exist_ok=True)
        ws.files_dir().mkdir(parents=True, exist_ok=True)

        skills = resolve_effective_skills(workspace_dir=ws.root, channel="console")

        kwargs: dict[str, Any] = {
            "skills": skills or None,
            "memory": get_memory_files(),
            "backend": FilesystemBackend(root_dir=str(ws.files_dir())),
            "checkpointer": ws.checkpointer,
            "store": get_store(),
        }
        if model is not None:
            kwargs["model"] = model
        return BoetClawAgentFactory.build(**kwargs)

    def build_agent_with_model(self, ws: Workspace, model: Any) -> Any:
        """Build a fresh workspace graph with an override model; does not cache it."""
        return self._build_agent(ws, model=model)

    async def get_agent(self, agent_id: str) -> Workspace:
        if agent_id != settings.default_agent_id and self.is_tombstoned(agent_id):
            raise ValueError(f"Agent 已删除：{agent_id}")

        ws = self._ws.get(agent_id)
        if ws and ws.agent is not None:
            ws.last_access = time.time()
            return ws

        async with self._lock(agent_id):
            if agent_id != settings.default_agent_id and self.is_tombstoned(agent_id):
                raise ValueError(f"Agent 已删除：{agent_id}")
            ws = self._ws.get(agent_id)
            if ws and ws.agent is not None:
                ws.last_access = time.time()
                return ws
            ws = Workspace(agent_id=agent_id, root=self._root / agent_id)
            from app.core.checkpoint import checkpoint_provider

            ws.checkpointer = await checkpoint_provider.get(agent_id)
            ws.agent = await asyncio.to_thread(self._build_agent, ws)
            ws.last_access = time.time()
            self._ws[agent_id] = ws
            logger.info("workspace_loaded", agent_id=agent_id)
            return ws

    async def reload_agent(self, agent_id: str) -> dict[str, Any]:
        """Rebuild a loaded workspace agent so skill changes take effect."""
        async with self._lock(agent_id):
            ws = self._ws.get(agent_id)
            if ws is None:
                ws = Workspace(agent_id=agent_id, root=self._root / agent_id)
                ws.root.mkdir(parents=True, exist_ok=True)
                ws.skills_dir().mkdir(parents=True, exist_ok=True)
                self._ws[agent_id] = ws
            was_loaded = ws.agent is not None
            ws.agent = None
            if was_loaded:
                from app.core.checkpoint import checkpoint_provider

                ws.checkpointer = await checkpoint_provider.get(agent_id)
                ws.agent = await asyncio.to_thread(self._build_agent, ws)
                ws.last_access = time.time()
                logger.info("workspace_reloaded", agent_id=agent_id)
            from app.agents.graph_cache import get_graph_cache

            get_graph_cache().invalidate_agent(agent_id)
            return {"agent_id": agent_id, "reloaded": was_loaded, "loaded": ws.agent is not None}

    async def reload_loaded_agents(self) -> list[dict[str, Any]]:
        """Reload all currently loaded workspace agents."""
        agent_ids = [agent_id for agent_id, ws in self._ws.items() if ws.agent is not None]
        return [await self.reload_agent(agent_id) for agent_id in agent_ids]

    def create(self, agent_id: str, config: dict[str, Any] | None = None) -> Workspace:
        if agent_id in self._ws and not self.is_tombstoned(agent_id):
            return self._ws[agent_id]
        ws = Workspace(agent_id=agent_id, root=self._root / agent_id, config=config or {})
        ws.root.mkdir(parents=True, exist_ok=True)
        self._deleted_marker(agent_id).unlink(missing_ok=True)
        self._purged_marker(agent_id).unlink(missing_ok=True)
        ws.skills_dir().mkdir(parents=True, exist_ok=True)
        self._ws[agent_id] = ws
        logger.info("workspace_created", agent_id=agent_id)
        return ws

    async def delete(self, agent_id: str, *, purge: bool = False) -> bool:
        if agent_id == settings.default_agent_id:
            raise ValueError("默认智能体不可删除")

        in_memory = agent_id in self._ws
        self._ws.pop(agent_id, None)
        from app.agents.graph_cache import get_graph_cache

        get_graph_cache().invalidate_agent(agent_id)
        root = self._root / agent_id
        exists_on_disk = root.is_dir()
        tombstoned = exists_on_disk and self.is_tombstoned(agent_id)

        if purge:
            from app.core.checkpoint import checkpoint_provider

            await checkpoint_provider.purge(agent_id)
            if exists_on_disk:
                shutil.rmtree(root)
            elif not in_memory and not self.was_purged(agent_id):
                return False
            marker = self._purged_marker(agent_id)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("purged\n", encoding="utf-8")
            logger.info("workspace_purged", agent_id=agent_id)
            return True

        if tombstoned or (not in_memory and not exists_on_disk):
            return False
        root.mkdir(parents=True, exist_ok=True)
        self._deleted_marker(agent_id).write_text("deleted\n", encoding="utf-8")
        logger.info("workspace_tombstoned", agent_id=agent_id)
        return True

    def list_agents(self) -> list[Workspace]:
        self._discover_disk()
        # Ensure default always present in listing
        if settings.default_agent_id not in self._ws:
            self.create(settings.default_agent_id)
        return [
            ws
            for ws in self._ws.values()
            if ws.agent_id == settings.default_agent_id or not self.is_tombstoned(ws.agent_id)
        ]

    def get_workspace(self, agent_id: str) -> Workspace | None:
        if agent_id == settings.default_agent_id:
            return self._ensure_workspace(agent_id)
        if self.is_tombstoned(agent_id) or self.was_purged(agent_id):
            return None
        if agent_id in self._ws:
            return self._ws[agent_id]
        if (self._root / agent_id).is_dir():
            return self._ensure_workspace(agent_id)
        return None

    def evict_idle(self, ttl_minutes: int | None = None) -> list[str]:
        ttl = (ttl_minutes if ttl_minutes is not None else settings.agent_idle_ttl_minutes) * 60
        now = time.time()
        evicted: list[str] = []
        for aid, ws in list(self._ws.items()):
            if aid == settings.default_agent_id:
                continue
            if ws.agent is not None and ws.last_access and (now - ws.last_access) > ttl:
                ws.agent = None
                evicted.append(aid)
        if evicted:
            logger.info("workspaces_evicted", agents=evicted)
        return evicted


multi_agent_manager = MultiAgentManager()
