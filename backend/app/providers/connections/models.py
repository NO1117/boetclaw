"""Provider connection models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

ConnectionSource = Literal["vault", "environment", "none"]

CONNECTIONS_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConnectionCheckResult:
    connected: bool
    detail: str
    error_category: str = ""
    latency_ms: float = 0.0
    model_count: int = 0
    checked_at: str = field(default_factory=_now_iso)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "detail": self.detail,
            "error_category": self.error_category,
            "latency_ms": round(self.latency_ms, 2),
            "model_count": self.model_count,
            "checked_at": self.checked_at,
        }


@dataclass
class ProviderConnection:
    id: str
    provider_type: str
    display_name: str
    base_url: str
    credential_id: str | None
    default_model: str
    enabled: bool
    timeout_seconds: int
    revision: int
    created_at: str
    updated_at: str
    is_default: bool = False
    last_check: ConnectionCheckResult | None = None

    def to_public_dict(
        self,
        *,
        credential_source: ConnectionSource = "none",
        credential_fingerprint: str = "",
        credential_configured: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_type": self.provider_type,
            "display_name": self.display_name,
            "base_url": self.base_url,
            "credential_id": self.credential_id,
            "credential_configured": credential_configured,
            "credential_source": credential_source,
            "credential_fingerprint": credential_fingerprint,
            "default_model": self.default_model,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "revision": self.revision,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_check": self.last_check.to_public_dict() if self.last_check else None,
        }

    @classmethod
    def from_storage(cls, raw: dict[str, Any], *, is_default: bool = False) -> ProviderConnection:
        last_check = None
        if isinstance(raw.get("last_check"), dict):
            lc = raw["last_check"]
            last_check = ConnectionCheckResult(
                connected=bool(lc.get("connected")),
                detail=str(lc.get("detail", "")),
                error_category=str(lc.get("error_category", "")),
                latency_ms=float(lc.get("latency_ms", 0) or 0),
                model_count=int(lc.get("model_count", 0) or 0),
                checked_at=str(lc.get("checked_at", _now_iso())),
            )
        return cls(
            id=str(raw["id"]),
            provider_type=str(raw["provider_type"]),
            display_name=str(raw.get("display_name", "")),
            base_url=str(raw.get("base_url", "")),
            credential_id=raw.get("credential_id") or None,
            default_model=str(raw.get("default_model", "")),
            enabled=bool(raw.get("enabled", True)),
            timeout_seconds=int(raw.get("timeout_seconds", 30) or 30),
            revision=int(raw.get("revision", 1) or 1),
            created_at=str(raw.get("created_at", _now_iso())),
            updated_at=str(raw.get("updated_at", _now_iso())),
            is_default=is_default,
            last_check=last_check,
        )

    def to_storage(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "provider_type": self.provider_type,
            "display_name": self.display_name,
            "base_url": self.base_url,
            "credential_id": self.credential_id,
            "default_model": self.default_model,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.last_check:
            out["last_check"] = self.last_check.to_public_dict()
        return out
