"""Atomic persistence for provider connections."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.observability import get_logger
from app.providers.connections.models import CONNECTIONS_SCHEMA_VERSION, ProviderConnection, _now_iso

logger = get_logger("connection_store")


class ConnectionStoreError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConnectionConflictError(ConnectionStoreError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"连接 revision 冲突：期望 {expected}，当前 {actual}", 409)
        self.expected_revision = expected
        self.actual_revision = actual


class ConnectionStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (settings.workspace_dir / "provider_connections.json")
        self._lock = threading.RLock()
        self._connections: dict[str, ProviderConnection] = {}
        self._default_connection_id: str | None = None
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_from_disk()
            self._loaded = True

    def _load_from_disk(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._connections = {}
            self._default_connection_id = None
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConnectionStoreError("连接配置文件损坏", 503) from exc
        if not isinstance(raw, dict):
            raise ConnectionStoreError("连接配置格式无效", 503)
        default_id = raw.get("default_connection_id")
        self._default_connection_id = str(default_id) if default_id else None
        entries = raw.get("connections", {})
        parsed: dict[str, ProviderConnection] = {}
        if isinstance(entries, dict):
            for cid, item in entries.items():
                if isinstance(item, dict):
                    parsed[str(cid)] = ProviderConnection.from_storage(
                        item,
                        is_default=str(cid) == self._default_connection_id,
                    )
        self._connections = parsed

    def _atomic_write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CONNECTIONS_SCHEMA_VERSION,
            "default_connection_id": self._default_connection_id,
            "connections": {cid: conn.to_storage() for cid, conn in self._connections.items()},
        }
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def list_all(self) -> list[ProviderConnection]:
        self._ensure_loaded()
        result: list[ProviderConnection] = []
        for conn in self._connections.values():
            result.append(
                ProviderConnection.from_storage(
                    conn.to_storage(),
                    is_default=conn.id == self._default_connection_id,
                )
            )
        return result

    def get(self, connection_id: str) -> ProviderConnection:
        self._ensure_loaded()
        conn = self._connections.get(connection_id)
        if conn is None:
            raise ConnectionStoreError("连接不存在", 404)
        return ProviderConnection.from_storage(
            conn.to_storage(),
            is_default=connection_id == self._default_connection_id,
        )

    def get_default_id(self) -> str | None:
        self._ensure_loaded()
        return self._default_connection_id

    def set_default_id(self, connection_id: str) -> None:
        self._ensure_loaded()
        if connection_id not in self._connections:
            raise ConnectionStoreError("连接不存在", 404)
        with self._lock:
            self._default_connection_id = connection_id
            self._atomic_write()

    def upsert(self, connection: ProviderConnection, *, expected_revision: int | None) -> ProviderConnection:
        self._ensure_loaded()
        with self._lock:
            existing = self._connections.get(connection.id)
            if existing is not None and expected_revision is not None:
                if existing.revision != expected_revision:
                    raise ConnectionConflictError(expected_revision, existing.revision)
            elif existing is None and expected_revision is not None and expected_revision != 0:
                raise ConnectionConflictError(expected_revision, 0)
            if existing is not None:
                connection.revision = existing.revision + 1
            else:
                connection.revision = max(1, connection.revision)
            connection.updated_at = _now_iso()
            connection.is_default = connection.id == self._default_connection_id
            self._connections[connection.id] = connection
            self._atomic_write()
            return ProviderConnection.from_storage(
                connection.to_storage(),
                is_default=connection.id == self._default_connection_id,
            )

    def delete(self, connection_id: str) -> ProviderConnection:
        self._ensure_loaded()
        with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn is None:
                raise ConnectionStoreError("连接不存在", 404)
            if self._default_connection_id == connection_id:
                self._default_connection_id = None
            self._atomic_write()
            return conn

    def replace_all(
        self,
        connections: dict[str, ProviderConnection],
        *,
        default_connection_id: str | None,
    ) -> None:
        with self._lock:
            self._connections = connections
            self._default_connection_id = default_connection_id
            self._atomic_write()
            self._loaded = True


connection_store = ConnectionStore()
