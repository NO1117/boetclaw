"""JSON-backed channel access control."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


class AccessControlStore:
    """Stores per-channel allowed user IDs.

    Empty or missing ``allowed_users`` means the channel is open, preserving the
    existing zero-configuration gateway behavior.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.workspace_dir / "access_control.json")

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"channels": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"channels": {}}
        return data if isinstance(data, dict) else {"channels": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_users(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def list(self) -> dict[str, Any]:
        data = self._load()
        channels = data.get("channels") if isinstance(data.get("channels"), dict) else {}
        normalized = {
            str(name): {"allowed_users": self._normalize_users(policy.get("allowed_users"))}
            for name, policy in channels.items()
            if isinstance(policy, dict)
        }
        return {"channels": normalized}

    def update(self, channels: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            str(name): {"allowed_users": self._normalize_users(policy.get("allowed_users"))}
            for name, policy in channels.items()
            if isinstance(policy, dict)
        }
        data = {"channels": normalized}
        self._save(data)
        return data

    def is_allowed(self, platform: str, user_id: str) -> bool:
        policy = self.list()["channels"].get(platform, {})
        allowed_users = policy.get("allowed_users", [])
        return not allowed_users or user_id in allowed_users


access_control_store = AccessControlStore()
