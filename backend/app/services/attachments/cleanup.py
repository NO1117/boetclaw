"""Reference-aware attachment cleanup."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.observability import get_logger
from app.services.attachments.service import attachment_service
from app.services.attachments.store import attachment_store

logger = get_logger("attachments.cleanup")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect_referenced_attachment_ids(sessions_root: Path | None = None) -> set[str]:
    root = sessions_root or (settings.workspace_dir / "sessions")
    referenced: set[str] = set()
    if not root.exists():
        return referenced
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for msg in data.get("messages", []):
            for item in msg.get("attachment_refs", []) or []:
                if isinstance(item, str):
                    referenced.add(item)
                elif isinstance(item, dict) and item.get("attachment_id"):
                    referenced.add(str(item["attachment_id"]))
    return referenced


def run_attachment_cleanup(*, dry_run: bool = False) -> dict[str, int]:
    referenced = collect_referenced_attachment_ids()
    now = datetime.now(timezone.utc)
    expired = 0
    skipped_ref = 0
    agents_root = attachment_store.root
    if not agents_root.exists():
        return {"expired": 0, "skipped_referenced": 0}

    for agent_dir in agents_root.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        for child in agent_dir.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / "meta.json"
            if not meta_path.exists():
                continue
            try:
                record = attachment_service.get_record(agent_id, child.name)
            except Exception:
                continue
            if record is None or record.status == "deleted":
                continue
            expires = _parse_iso(record.expires_at)
            if expires is None or expires > now:
                continue
            if record.attachment_id in referenced:
                skipped_ref += 1
                continue
            expired += 1
            if not dry_run:
                try:
                    import asyncio

                    asyncio.get_event_loop().run_until_complete(
                        attachment_service.delete(agent_id, record.attachment_id, reason="expired")
                    )
                except RuntimeError:
                    import asyncio

                    asyncio.run(attachment_service.delete(agent_id, record.attachment_id, reason="expired"))
                logger.info("attachment_expired", attachment_id=record.attachment_id, agent_id=agent_id)
    return {"expired": expired, "skipped_referenced": skipped_ref}
