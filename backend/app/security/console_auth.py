"""HMAC-signed token helpers for console and user sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.core.config import settings

TOKEN_COOKIE = "boetclaw_console_token"
CSRF_COOKIE = "boetclaw_csrf"
CSRF_HEADER = "x-csrf-token"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _secret() -> bytes:
    secret = (
        settings.console_jwt_secret
        or settings.api_token
        or settings.console_password
        or "boetclaw-dev-insecure"
    )
    return secret.encode("utf-8")


def _sign(header: dict[str, Any], payload: dict[str, Any]) -> str:
    signing_input = (
        f"{_b64encode(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64encode(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def _verify(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = hmac.new(_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        actual = _b64decode(parts[2])
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(expected, actual):
        return None
    try:
        payload = json.loads(_b64decode(parts[1]).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload if isinstance(payload, dict) else None


def create_console_token(subject: str = "console") -> str:
    now = int(time.time())
    ttl_seconds = max(settings.console_jwt_ttl_minutes, 1) * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + ttl_seconds,
        "scope": "console",
        "jti": uuid.uuid4().hex,
    }
    return _sign(header, payload)


def verify_console_token(token: str) -> dict[str, Any] | None:
    """Verify legacy console-scope token (CONSOLE_PASSWORD login)."""
    payload = _verify(token)
    if not payload:
        return None
    if payload.get("scope") != "console":
        return None
    # Require some auth config OR accept when verifying purely for signature.
    return payload


def create_user_token(
    *,
    user_id: str,
    role: str,
    token_version: int,
    session_id: str,
    ttl_minutes: int | None = None,
) -> str:
    now = int(time.time())
    ttl = max(ttl_minutes or settings.console_jwt_ttl_minutes, 1) * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "role": role,
        "tv": token_version,
        "sid": session_id,
        "iat": now,
        "exp": now + ttl,
        "scope": "user",
        "jti": uuid.uuid4().hex,
    }
    return _sign(header, payload)


def verify_user_token(token: str) -> dict[str, Any] | None:
    payload = _verify(token)
    if not payload:
        return None
    if payload.get("scope") != "user":
        return None
    return payload


def extract_bearer_token(authorization: str) -> str:
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""
