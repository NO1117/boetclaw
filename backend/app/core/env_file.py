"""Helpers for updating the local .env file."""

from __future__ import annotations

from pathlib import Path

from app.core.config import BASE_DIR


def _format_env_value(value: str) -> str:
    clean = value.replace("\r", " ").replace("\n", " ")
    if not clean or any(ch.isspace() for ch in clean) or "#" in clean:
        return '"' + clean.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return clean


def update_env_file(values: dict[str, str], path: Path | None = None) -> None:
    """Update or append key/value pairs while preserving unrelated .env lines."""
    env_path = path or (BASE_DIR / ".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = {key.upper(): str(value) for key, value in values.items()}
    updated: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        prefix = line[: len(line) - len(stripped)]
        candidate = stripped[1:].lstrip() if stripped.startswith("#") else stripped
        if "=" not in candidate:
            updated.append(line)
            continue
        key, _, _ = candidate.partition("=")
        normalized = key.strip().upper()
        if normalized in remaining:
            updated.append(f"{prefix}{normalized}={_format_env_value(remaining.pop(normalized))}")
        else:
            updated.append(line)

    for key, value in remaining.items():
        updated.append(f"{key}={_format_env_value(value)}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
