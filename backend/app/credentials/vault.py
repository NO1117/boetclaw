"""AEAD credential vault with atomic persistence."""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.observability import get_logger
from app.credentials.master_key import MasterKeyError, load_master_key, master_key_configured
from app.credentials.models import (
    ALGORITHM_AES_GCM_V1,
    CredentialMeta,
    DecryptedCredential,
    StoredCredentialRecord,
    VAULT_SCHEMA_VERSION,
    VaultStatus,
    _now_iso,
)

logger = get_logger("credential_vault")


class CredentialVaultError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class CredentialVault:
    """Encrypted local credential store using AES-256-GCM."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (settings.workspace_dir / "credentials" / "vault.json")
        self._quarantine_dir = self._path.parent / "quarantine"
        self._lock = threading.RLock()
        self._records: dict[str, StoredCredentialRecord] = {}
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_from_disk()
            self._loaded = True

    def _load_from_disk(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._records = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._quarantine_corrupt(self._path, reason="json_decode")
            raise CredentialVaultError("凭据保险箱文件损坏，已隔离", 503) from exc
        if not isinstance(raw, dict):
            self._quarantine_corrupt(self._path, reason="invalid_root")
            raise CredentialVaultError("凭据保险箱格式无效", 503)
        entries = raw.get("credentials", {})
        if not isinstance(entries, dict):
            raise CredentialVaultError("凭据保险箱格式无效", 503)
        parsed: dict[str, StoredCredentialRecord] = {}
        for cred_id, item in entries.items():
            if not isinstance(item, dict):
                continue
            try:
                record = StoredCredentialRecord.from_storage(item)
                parsed[str(cred_id)] = record
            except (KeyError, TypeError, ValueError):
                logger.warning("credential_record_skipped", credential_id=str(cred_id))
        self._records = parsed

    def _quarantine_corrupt(self, path: Path, *, reason: str) -> None:
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        target = self._quarantine_dir / f"vault.{stamp}.{reason}.json"
        try:
            path.replace(target)
        except OSError:
            logger.error("vault_quarantine_failed", reason=reason)
        self._records = {}

    def _require_key(self) -> bytes:
        key = load_master_key()
        if key is None:
            raise CredentialVaultError(
                "未配置 BOETCLAW_MASTER_KEY，凭据保险箱写入已禁用。"
                "请设置 32 字节主密钥后重试，或继续使用环境变量凭据。",
                503,
            )
        return key

    def _encrypt(self, payload: dict[str, str]) -> tuple[str, str]:
        key = self._require_key()
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        import base64

        return base64.urlsafe_b64encode(nonce).decode("ascii"), base64.urlsafe_b64encode(ciphertext).decode("ascii")

    def _decrypt(self, record: StoredCredentialRecord) -> dict[str, str]:
        key = load_master_key()
        if key is None:
            raise CredentialVaultError("未配置 BOETCLAW_MASTER_KEY，无法解密凭据", 503)
        import base64

        try:
            nonce = base64.urlsafe_b64decode(record.nonce_b64 + "=" * (-len(record.nonce_b64) % 4))
            ciphertext = base64.urlsafe_b64decode(record.ciphertext_b64 + "=" * (-len(record.ciphertext_b64) % 4))
        except Exception as exc:
            raise CredentialVaultError("凭据密文格式无效", 503) from exc
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise CredentialVaultError("凭据解密失败，主密钥可能不正确", 503) from exc
        data = json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            raise CredentialVaultError("凭据载荷格式无效", 503)
        return {str(k): str(v) for k, v in data.items()}

    def _atomic_write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": VAULT_SCHEMA_VERSION,
            "credentials": {cid: rec.to_storage() for cid, rec in self._records.items()},
        }
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def status(self) -> VaultStatus:
        self._ensure_loaded()
        configured = master_key_configured()
        writable = configured
        message = ""
        if not configured:
            message = "未配置 BOETCLAW_MASTER_KEY；保险箱写入已禁用，环境变量凭据仍可用。"
        return VaultStatus(
            configured=configured,
            writable=writable,
            credential_count=len(self._records),
            message=message,
        )

    def list_meta(self) -> list[CredentialMeta]:
        self._ensure_loaded()
        return [rec.meta for rec in self._records.values()]

    def get_meta(self, credential_id: str) -> CredentialMeta:
        self._ensure_loaded()
        rec = self._records.get(credential_id)
        if rec is None:
            raise CredentialVaultError("凭据不存在", 404)
        return rec.meta

    def create(
        self,
        *,
        purpose: str,
        payload: dict[str, str],
        label: str = "",
        credential_id: str | None = None,
    ) -> CredentialMeta:
        self._ensure_loaded()
        if not payload:
            raise CredentialVaultError("凭据载荷不能为空")
        cred_id = credential_id or f"cred_{uuid.uuid4().hex[:16]}"
        if cred_id in self._records:
            raise CredentialVaultError("凭据 ID 已存在", 409)
        now = _now_iso()
        nonce_b64, ciphertext_b64 = self._encrypt(payload)
        meta = CredentialMeta(
            id=cred_id,
            purpose=purpose,
            algorithm=ALGORITHM_AES_GCM_V1,
            label=label,
            created_at=now,
            updated_at=now,
            ref_count=0,
        )
        with self._lock:
            self._records[cred_id] = StoredCredentialRecord(
                schema_version=VAULT_SCHEMA_VERSION,
                meta=meta,
                nonce_b64=nonce_b64,
                ciphertext_b64=ciphertext_b64,
            )
            self._atomic_write()
        logger.info("credential_created", credential_id=cred_id, purpose=purpose)
        return meta

    def replace(self, credential_id: str, *, payload: dict[str, str], label: str | None = None) -> CredentialMeta:
        self._ensure_loaded()
        with self._lock:
            rec = self._records.get(credential_id)
            if rec is None:
                raise CredentialVaultError("凭据不存在", 404)
            nonce_b64, ciphertext_b64 = self._encrypt(payload)
            now = _now_iso()
            meta = CredentialMeta(
                id=credential_id,
                purpose=rec.meta.purpose,
                algorithm=ALGORITHM_AES_GCM_V1,
                label=label if label is not None else rec.meta.label,
                created_at=rec.meta.created_at,
                updated_at=now,
                ref_count=rec.meta.ref_count,
            )
            self._records[credential_id] = StoredCredentialRecord(
                schema_version=VAULT_SCHEMA_VERSION,
                meta=meta,
                nonce_b64=nonce_b64,
                ciphertext_b64=ciphertext_b64,
            )
            self._atomic_write()
        logger.info("credential_replaced", credential_id=credential_id)
        return meta

    def delete(self, credential_id: str) -> None:
        self._ensure_loaded()
        with self._lock:
            rec = self._records.get(credential_id)
            if rec is None:
                raise CredentialVaultError("凭据不存在", 404)
            if rec.meta.ref_count > 0:
                raise CredentialVaultError("凭据仍被连接引用，无法删除", 409)
            del self._records[credential_id]
            self._atomic_write()
        logger.info("credential_deleted", credential_id=credential_id)

    def increment_ref(self, credential_id: str, delta: int = 1) -> None:
        self._ensure_loaded()
        with self._lock:
            rec = self._records.get(credential_id)
            if rec is None:
                raise CredentialVaultError("凭据不存在", 404)
            new_count = max(0, rec.meta.ref_count + delta)
            rec.meta.ref_count = new_count
            rec.meta.updated_at = _now_iso()
            self._atomic_write()

    def use_ephemeral(self, credential_id: str) -> DecryptedCredential:
        """Decrypt for immediate use; caller must not retain or log payload."""
        self._ensure_loaded()
        rec = self._records.get(credential_id)
        if rec is None:
            raise CredentialVaultError("凭据不存在", 404)
        payload = self._decrypt(rec)
        return DecryptedCredential(meta=rec.meta, payload=payload)

    def rotate_master_key(self, new_key: bytes) -> int:
        """Re-encrypt all credentials with a new 32-byte key. Caller updates env separately."""
        if len(new_key) != 32:
            raise MasterKeyError("新主密钥长度必须为 32 字节")
        self._ensure_loaded()
        decrypted: list[tuple[str, dict[str, str], CredentialMeta]] = []
        for cred_id, rec in self._records.items():
            payload = self._decrypt(rec)
            decrypted.append((cred_id, payload, rec.meta))
        import base64

        aesgcm = AESGCM(new_key)
        with self._lock:
            for cred_id, payload, meta in decrypted:
                nonce = secrets.token_bytes(12)
                plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                ciphertext = aesgcm.encrypt(nonce, plaintext, None)
                now = _now_iso()
                updated_meta = CredentialMeta(
                    id=meta.id,
                    purpose=meta.purpose,
                    algorithm=ALGORITHM_AES_GCM_V1,
                    label=meta.label,
                    created_at=meta.created_at,
                    updated_at=now,
                    ref_count=meta.ref_count,
                )
                self._records[cred_id] = StoredCredentialRecord(
                    schema_version=VAULT_SCHEMA_VERSION,
                    meta=updated_meta,
                    nonce_b64=base64.urlsafe_b64encode(nonce).decode("ascii"),
                    ciphertext_b64=base64.urlsafe_b64encode(ciphertext).decode("ascii"),
                )
            self._atomic_write()
        logger.info("vault_key_rotated", count=len(decrypted))
        return len(decrypted)


credential_vault = CredentialVault()
