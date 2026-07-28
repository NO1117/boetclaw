"""Username normalization to avoid case / whitespace / Unicode confusion."""

from __future__ import annotations

import re
import unicodedata

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}[a-z0-9]$|^[a-z0-9]{2,64}$")


def normalize_username(username: str) -> str:
    if username is None:
        raise ValueError("username is required")
    # NFKC collapses compatibility forms; casefold for case-insensitive uniqueness.
    cleaned = unicodedata.normalize("NFKC", username).strip().casefold()
    # Collapse internal whitespace to nothing (usernames disallow spaces).
    cleaned = "".join(cleaned.split())
    if not cleaned:
        raise ValueError("username is required")
    if not _USERNAME_RE.match(cleaned):
        raise ValueError(
            "username must be 2-64 chars: lowercase letters, digits, . _ - "
            "(must start/end with alphanumeric)"
        )
    return cleaned


def validate_display_name(display_name: str) -> str:
    name = unicodedata.normalize("NFKC", display_name or "").strip()
    if not name:
        raise ValueError("display_name is required")
    if len(name) > 128:
        raise ValueError("display_name too long")
    return name
