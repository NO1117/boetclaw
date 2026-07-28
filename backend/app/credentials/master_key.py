"""Parse BOETCLAW_MASTER_KEY from the environment."""

from __future__ import annotations

import base64
import binascii
import os
from functools import lru_cache


class MasterKeyError(ValueError):
    pass


def _decode_key(raw: str) -> bytes:
    text = raw.strip()
    if not text:
        raise MasterKeyError("主密钥为空")
    # Try base64 / base64url
    for decoder in (
        lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)),
        lambda s: base64.b64decode(s + "=" * (-len(s) % 4)),
    ):
        try:
            key = decoder(text)
            if len(key) == 32:
                return key
        except (binascii.Error, ValueError):
            continue
    # Hex fallback
    try:
        key = bytes.fromhex(text)
        if len(key) == 32:
            return key
    except ValueError as exc:
        raise MasterKeyError("主密钥格式无效，需要 32 字节 base64 或 hex") from exc
    raise MasterKeyError("主密钥长度必须为 32 字节")


@lru_cache(maxsize=1)
def load_master_key() -> bytes | None:
    raw = os.environ.get("BOETCLAW_MASTER_KEY", "").strip()
    if not raw:
        return None
    return _decode_key(raw)


def master_key_configured() -> bool:
    return load_master_key() is not None


def clear_master_key_cache() -> None:
    load_master_key.cache_clear()
