"""Context policy: decide memory persistence by request source."""

from __future__ import annotations

# Sources that are machine-triggered and must NOT pollute long-term memory.
AUTOMATION_SKIP_SOURCES = {"cron", "heartbeat"}

# All recognized request sources.
KNOWN_SOURCES = {"user", "channel", "cron", "heartbeat"}


def normalize_source(source: str | None) -> str:
    if not source:
        return "user"
    s = source.strip().lower()
    return s if s in KNOWN_SOURCES else "user"


def should_persist_memory(source: str | None) -> bool:
    """Whether a request from this source should write long-term memory."""
    return normalize_source(source) not in AUTOMATION_SKIP_SOURCES


def is_automation(source: str | None) -> bool:
    return normalize_source(source) in AUTOMATION_SKIP_SOURCES
