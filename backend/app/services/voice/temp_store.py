"""Controlled temporary storage for voice uploads."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from app.core.config import settings
from app.providers.speech.errors import VoiceError, VOICE_UNSUPPORTED_FORMAT


class VoiceTempStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (settings.workspace_dir / ".cache" / "voice_temp")
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, name: str) -> Path:
        candidate = (self.root / name).resolve()
        root = self.root.resolve()
        if not str(candidate).startswith(str(root)):
            raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "非法临时路径")
        return candidate

    def allocate(self, ext: str) -> tuple[Path, str]:
        token = secrets.token_hex(16)
        safe_ext = ext if ext.startswith(".") else f".{ext}"
        filename = f"{token}{safe_ext}"
        path = self._safe_path(filename)
        path.write_bytes(b"")
        return path, filename

    def write(self, path: Path, data: bytes) -> None:
        resolved = path.resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "非法临时路径")
        resolved.write_bytes(data)

    def remove(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if str(resolved).startswith(str(self.root.resolve())) and resolved.exists():
                resolved.unlink(missing_ok=True)
        except OSError:
            pass

    def cleanup_stale(self, max_age_seconds: int | None = None) -> int:
        ttl = max_age_seconds if max_age_seconds is not None else settings.speech_temp_ttl_seconds
        cutoff = time.time() - ttl
        removed = 0
        for item in self.root.glob("*"):
            if not item.is_file():
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    item.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
        return removed


voice_temp_store = VoiceTempStore()
