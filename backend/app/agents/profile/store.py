"""Atomic agent.json persistence with schema migration and backup."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.agents.profile.models import CURRENT_SCHEMA_VERSION, AgentProfile
from app.agents.profile.security import ProfileSecurityError, resolve_profile_file
from app.core.config import settings
from app.core.observability import get_logger

logger = get_logger("agent_profile_store")


class ProfileStoreError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProfileConflictError(ProfileStoreError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"配置 revision 冲突：期望 {expected}，当前 {actual}", 409)
        self.expected_revision = expected
        self.actual_revision = actual


class ProfileStore:
    def __init__(self, agents_root: Path | None = None) -> None:
        self._root = agents_root or settings.agents_root
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _lock(self, agent_id: str) -> threading.Lock:
        with self._global_lock:
            if agent_id not in self._locks:
                self._locks[agent_id] = threading.Lock()
            return self._locks[agent_id]

    def profile_path(self, agent_id: str) -> Path:
        return resolve_profile_file(self._root, agent_id)

    def backup_path(self, agent_id: str) -> Path:
        return self.profile_path(agent_id).with_suffix(".json.bak")

    def apply_state_path(self, agent_id: str) -> Path:
        return resolve_profile_file(self._root, agent_id).parent / ".profile" / "apply_state.json"

    def _migrate(self, raw: dict[str, Any]) -> dict[str, Any]:
        version = int(raw.get("schema_version", 0) or 0)
        if version == 0:
            migrated = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "agent_id": raw.get("agent_id", ""),
                "display_name": raw.get("display_name", raw.get("name", "")),
                "description": raw.get("description", ""),
                "avatar_color": raw.get("avatar_color", "#6366f1"),
                "system_prompt": raw.get("system_prompt", raw.get("prompt", "")),
                "provider": raw.get("provider", ""),
                "model": raw.get("model", ""),
                "temperature": raw.get("temperature"),
                "max_output_tokens": raw.get("max_output_tokens"),
                "tool_policy": raw.get("tool_policy", "inherit"),
                "tool_allowlist": raw.get("tool_allowlist", []),
                "memory_mode": raw.get("memory_mode", "inherit"),
                "default_language": raw.get("default_language", "zh"),
                "enabled": raw.get("enabled", True),
                "revision": raw.get("revision", 1),
                "created_at": raw.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "updated_at": raw.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            }
            return migrated
        if version > CURRENT_SCHEMA_VERSION:
            raise ProfileStoreError(f"不支持的 schema 版本: {version}")
        return raw

    def _read_raw(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ProfileStoreError("Agent 配置不存在", 404)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileStoreError("agent.json 格式无效") from exc
        if not isinstance(raw, dict):
            raise ProfileStoreError("agent.json 必须是 JSON 对象")
        return self._migrate(raw)

    def load(self, agent_id: str, *, create_default: bool = False) -> AgentProfile:
        path = self.profile_path(agent_id)
        if not path.exists():
            if not create_default:
                raise ProfileStoreError("Agent 配置不存在", 404)
            profile = AgentProfile.default_for(agent_id)
            self.save(profile, expected_revision=None)
            return profile
        raw = self._read_raw(path)
        try:
            return AgentProfile.model_validate(raw)
        except ValidationError as exc:
            raise ProfileStoreError(f"Agent 配置无效: {exc}") from exc

    def exists(self, agent_id: str) -> bool:
        return self.profile_path(agent_id).exists()

    def save(self, profile: AgentProfile, *, expected_revision: int | None) -> AgentProfile:
        agent_id = profile.agent_id
        with self._lock(agent_id):
            path = self.profile_path(agent_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            if expected_revision is not None and path.exists():
                current_rev = int(self._read_raw(path).get("revision", 1))
                if current_rev != expected_revision:
                    raise ProfileConflictError(expected_revision, current_rev)
            profile.schema_version = CURRENT_SCHEMA_VERSION
            profile.updated_at = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(profile.to_disk_dict(), ensure_ascii=False, indent=2)
            if path.exists():
                self.backup_path(agent_id).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
            logger.info("agent_profile_saved", agent_id=agent_id, revision=profile.revision)
            return profile

    def restore_backup(self, agent_id: str) -> AgentProfile | None:
        backup = self.backup_path(agent_id)
        path = self.profile_path(agent_id)
        if not backup.exists():
            return None
        with self._lock(agent_id):
            os.replace(backup, path)
            return self.load(agent_id)

    def read_apply_state(self, agent_id: str) -> dict[str, Any]:
        path = self.apply_state_path(agent_id)
        if not path.exists():
            return {"revision": 0, "status": "pending", "applied_at": "", "error_summary": ""}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {"revision": 0, "status": "failed", "applied_at": "", "error_summary": "apply_state 损坏"}

    def write_apply_state(self, agent_id: str, state: dict[str, Any]) -> None:
        path = self.apply_state_path(agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def discover_profiles(self) -> list[str]:
        if not self._root.is_dir():
            return []
        ids: list[str] = []
        for child in self._root.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            if (child / "agent.json").exists():
                try:
                    ids.append(validate_agent_id_safe(child.name))
                except ProfileSecurityError:
                    continue
        return ids


def validate_agent_id_safe(agent_id: str) -> str:
    from app.agents.profile.security import validate_agent_id

    return validate_agent_id(agent_id)
