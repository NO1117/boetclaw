"""Agent profile security: ID validation, path safety and secret detection."""

from __future__ import annotations

import re
from pathlib import Path

from app.memory.sensitive import contains_sensitive_content

_SAFE_AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "token",
        "password",
        "private_key",
        "connection_string",
        "openai_api_key",
        "anthropic_api_key",
        "google_api_key",
    }
)
_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:\\|^/|^\\\\")


class ProfileSecurityError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_agent_id(agent_id: str) -> str:
    value = (agent_id or "").strip()
    if not value or not _SAFE_AGENT_ID.match(value):
        raise ProfileSecurityError("无效的 Agent ID，仅支持字母、数字、下划线与连字符")
    if ".." in value or value.startswith("."):
        raise ProfileSecurityError("无效的 Agent ID")
    return value


def resolve_agent_root(agents_root: Path, agent_id: str) -> Path:
    safe_id = validate_agent_id(agent_id)
    root = (agents_root / safe_id).resolve()
    base = agents_root.resolve()
    if root != base and base not in root.parents:
        raise ProfileSecurityError("Agent 路径越界")
    return root


def resolve_profile_file(agents_root: Path, agent_id: str) -> Path:
    return resolve_agent_root(agents_root, agent_id) / "agent.json"


def scan_profile_secrets(payload: dict) -> list[str]:
    errors: list[str] = []

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_lower = str(key).lower()
                if key_lower in _SECRET_FIELD_NAMES:
                    errors.append(f"不允许的配置字段: {prefix}{key}")
                    continue
                walk(f"{prefix}{key}.", nested)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(f"{prefix}[{index}].", item)
            return
        if isinstance(value, str):
            if _ABSOLUTE_PATH.match(value.strip()):
                errors.append(f"不允许绝对路径: {prefix.rstrip('.')}")
            if contains_sensitive_content(value):
                errors.append(f"检测到疑似密钥或凭据: {prefix.rstrip('.')}")

    walk("", payload)
    return errors
