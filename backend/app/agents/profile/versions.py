"""Version history repository for AgentProfile."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.profile.models import ProfileVersionRecord
from app.agents.profile.security import resolve_agent_root
from app.core.config import settings


class VersionRepository:
    def __init__(self, agents_root: Path | None = None) -> None:
        self._root = agents_root or settings.agents_root

    def _versions_dir(self, agent_id: str) -> Path:
        return resolve_agent_root(self._root, agent_id) / ".profile" / "versions"

    def append(self, record: ProfileVersionRecord) -> None:
        directory = self._versions_dir(record.snapshot.get("agent_id", ""))
        if not record.snapshot.get("agent_id"):
            raise ValueError("version snapshot requires agent_id")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record.revision:06d}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def list_revisions(self, agent_id: str, *, offset: int = 0, limit: int = 20) -> tuple[list[dict[str, Any]], int]:
        directory = self._versions_dir(agent_id)
        if not directory.is_dir():
            return [], 0
        files = sorted(directory.glob("*.json"), reverse=True)
        total = len(files)
        rows: list[dict[str, Any]] = []
        for path in files[offset : offset + limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            rows.append(
                {
                    "revision": data.get("revision"),
                    "created_at": data.get("created_at"),
                    "changed_fields": data.get("changed_fields", []),
                    "operator": data.get("operator", "system"),
                }
            )
        return rows, total

    def get(self, agent_id: str, revision: int) -> ProfileVersionRecord | None:
        path = self._versions_dir(agent_id) / f"{revision:06d}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProfileVersionRecord.model_validate(data)

    @staticmethod
    def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        keys = sorted(set(before.keys()) | set(after.keys()))
        changed: list[str] = []
        for key in keys:
            if before.get(key) != after.get(key):
                changed.append(key)
        return changed

    @staticmethod
    def make_record(
        *,
        profile_dict: dict[str, Any],
        previous: dict[str, Any] | None,
        operator: str = "system",
    ) -> ProfileVersionRecord:
        changed = VersionRepository.diff_fields(previous or {}, profile_dict) if previous else list(profile_dict.keys())
        return ProfileVersionRecord(
            revision=int(profile_dict.get("revision", 1)),
            created_at=datetime.now(timezone.utc).isoformat(),
            changed_fields=changed,
            operator=operator,
            snapshot=profile_dict,
        )
