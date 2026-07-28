"""Credential vault record models (no plaintext in repr)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


VAULT_SCHEMA_VERSION = 1
ALGORITHM_AES_GCM_V1 = "aes-256-gcm-v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CredentialMeta:
    id: str
    purpose: str
    algorithm: str
    label: str
    created_at: str
    updated_at: str
    ref_count: int = 0

    def __repr__(self) -> str:
        return f"CredentialMeta(id={self.id!r}, purpose={self.purpose!r}, ref_count={self.ref_count})"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "algorithm": self.algorithm,
            "label": self.label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ref_count": self.ref_count,
        }

    @classmethod
    def from_storage(cls, raw: dict[str, Any]) -> CredentialMeta:
        return cls(
            id=str(raw["id"]),
            purpose=str(raw.get("purpose", "provider_api_key")),
            algorithm=str(raw.get("algorithm", ALGORITHM_AES_GCM_V1)),
            label=str(raw.get("label", "")),
            created_at=str(raw.get("created_at", _now_iso())),
            updated_at=str(raw.get("updated_at", _now_iso())),
            ref_count=int(raw.get("ref_count", 0) or 0),
        )


@dataclass
class StoredCredentialRecord:
    schema_version: int
    meta: CredentialMeta
    nonce_b64: str
    ciphertext_b64: str

    def to_storage(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.meta.id,
            "purpose": self.meta.purpose,
            "algorithm": self.meta.algorithm,
            "label": self.meta.label,
            "nonce": self.nonce_b64,
            "ciphertext": self.ciphertext_b64,
            "created_at": self.meta.created_at,
            "updated_at": self.meta.updated_at,
            "ref_count": self.meta.ref_count,
        }

    @classmethod
    def from_storage(cls, raw: dict[str, Any]) -> StoredCredentialRecord:
        meta = CredentialMeta.from_storage(raw)
        return cls(
            schema_version=int(raw.get("schema_version", VAULT_SCHEMA_VERSION)),
            meta=meta,
            nonce_b64=str(raw["nonce"]),
            ciphertext_b64=str(raw["ciphertext"]),
        )


@dataclass
class VaultStatus:
    configured: bool
    writable: bool
    credential_count: int
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "writable": self.writable,
            "credential_count": self.credential_count,
            "message": self.message,
        }


@dataclass
class DecryptedCredential:
    """Ephemeral decrypted payload; never log or serialize."""

    meta: CredentialMeta
    payload: dict[str, str] = field(repr=False)

    def __repr__(self) -> str:
        return f"DecryptedCredential(id={self.meta.id!r})"

    def api_key(self) -> str:
        return self.payload.get("api_key", "")
