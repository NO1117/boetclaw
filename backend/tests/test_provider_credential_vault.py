"""Tests for credential vault and provider connections."""

from __future__ import annotations

import base64
import json
import os

import pytest
from fastapi.testclient import TestClient
@pytest.fixture
def isolated_paths(tmp_path, monkeypatch, master_key):
    vault_path = tmp_path / "credentials" / "vault.json"
    conn_path = tmp_path / "provider_connections.json"
    monkeypatch.setattr("app.credentials.vault.credential_vault._path", vault_path)
    monkeypatch.setattr("app.credentials.vault.credential_vault._loaded", False)
    monkeypatch.setattr("app.credentials.vault.credential_vault._records", {})
    monkeypatch.setattr("app.providers.connections.store.connection_store._path", conn_path)
    monkeypatch.setattr("app.providers.connections.store.connection_store._loaded", False)
    monkeypatch.setattr("app.providers.connections.store.connection_store._connections", {})
    monkeypatch.setattr("app.providers.connections.store.connection_store._default_connection_id", None)
    return tmp_path


def test_vault_encrypt_decrypt_roundtrip(isolated_paths, master_key):
    from app.credentials.vault import credential_vault

    meta = credential_vault.create(
        purpose="provider_api_key",
        payload={"api_key": "sk-test-secret-key-1234"},
        label="test",
    )
    dec = credential_vault.use_ephemeral(meta.id)
    assert dec.api_key() == "sk-test-secret-key-1234"
    assert "sk-test" not in repr(dec)
    assert "sk-test" not in meta.to_public_dict().values()


def test_vault_tamper_detection(isolated_paths, master_key):
    from app.credentials.vault import CredentialVaultError, credential_vault

    meta = credential_vault.create(
        purpose="provider_api_key",
        payload={"api_key": "sk-tamper"},
        label="test",
    )
    raw = json.loads(credential_vault.path.read_text(encoding="utf-8"))
    raw["credentials"][meta.id]["ciphertext"] = "AAAA"
    credential_vault.path.write_text(json.dumps(raw), encoding="utf-8")
    credential_vault._loaded = False
    with pytest.raises(CredentialVaultError, match="解密失败"):
        credential_vault.use_ephemeral(meta.id)


def test_vault_no_master_key_write_disabled(isolated_paths, monkeypatch):
    monkeypatch.delenv("BOETCLAW_MASTER_KEY", raising=False)
    from app.credentials.master_key import clear_master_key_cache
    from app.credentials.vault import CredentialVaultError, credential_vault

    clear_master_key_cache()
    credential_vault._loaded = False
    status = credential_vault.status()
    assert status.configured is False
    assert status.writable is False
    with pytest.raises(CredentialVaultError, match="BOETCLAW_MASTER_KEY"):
        credential_vault.create(purpose="provider_api_key", payload={"api_key": "sk-x"})


def test_vault_key_rotation(isolated_paths, master_key, monkeypatch):
    from app.credentials.master_key import clear_master_key_cache, load_master_key
    from app.credentials.vault import credential_vault

    meta = credential_vault.create(
        purpose="provider_api_key",
        payload={"api_key": "sk-rotate-me"},
        label="rotate",
    )
    new_key = os.urandom(32)
    credential_vault.rotate_master_key(new_key)
    monkeypatch.setenv("BOETCLAW_MASTER_KEY", base64.urlsafe_b64encode(new_key).decode("ascii").rstrip("="))
    clear_master_key_cache()
    credential_vault._loaded = False
    assert credential_vault.use_ephemeral(meta.id).api_key() == "sk-rotate-me"
    assert load_master_key() == new_key


def test_connection_crud_and_no_secret_leak(isolated_paths, master_key):
    from app.providers.connections.service import connection_service

    created = connection_service.create_connection(
        provider_type="openai",
        display_name="Prod OpenAI",
        api_key="sk-prod-key-9999",
        default_model="gpt-4o",
        set_default=True,
    )
    assert created["credential_configured"] is True
    assert created["credential_fingerprint"] == "9999"
    assert "sk-prod" not in json.dumps(created)
    listed = connection_service.list_connections()
    assert len(listed) == 1
    assert "api_key" not in listed[0]


def test_connection_revision_conflict(isolated_paths, master_key):
    from app.providers.connections.service import ConnectionServiceError, connection_service

    conn = connection_service.create_connection(
        provider_type="openai",
        display_name="A",
        api_key="sk-a",
        default_model="gpt-4o",
    )
    cid = conn["id"]
    with pytest.raises(ConnectionServiceError) as exc:
        connection_service.update_connection(
            cid,
            display_name="B",
            expected_revision=999,
        )
    assert exc.value.status_code == 409


def test_connection_delete_reference_protection(isolated_paths, master_key):
    from app.providers.connections.service import ConnectionReferenceError, connection_service

    conn = connection_service.create_connection(
        provider_type="openai",
        display_name="Default",
        api_key="sk-ref",
        default_model="gpt-4o",
        set_default=True,
    )
    with pytest.raises(ConnectionReferenceError) as exc:
        connection_service.delete_connection(conn["id"])
    assert exc.value.status_code == 409
    assert any(r["kind"] == "default_connection" for r in exc.value.references)


def test_import_env_does_not_modify_env_file(isolated_paths, master_key, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.providers.connections.service import connection_service

    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-from-env\n", encoding="utf-8")
    monkeypatch.setattr(settings, "openai_api_key", "sk-from-env", raising=False)
    result = connection_service.import_from_env()
    assert result["count"] >= 1
    assert result["env_cleanup_required"] is True
    assert env_path.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-from-env\n"


def test_provider_routes_no_env_api_key_write(isolated_paths, master_key, monkeypatch, tmp_path):
    from app.api.routes import providers as provider_routes
    from app.core.config import settings
    from app.main import app

    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=\nOPENAI_BASE_URL=\n", encoding="utf-8")
    monkeypatch.setattr(provider_routes, "PROVIDER_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(settings, "openai_base_url", "", raising=False)

    client = TestClient(app)
    res = client.put(
        "/api/v1/providers/openai/config",
        json={"api_key": "sk-vault-only", "base_url": "http://localhost:8001/v1"},
    )
    assert res.status_code == 200
    assert res.json()["api_key_configured"] is True
    assert "sk-vault" not in res.text
    content = env_path.read_text(encoding="utf-8")
    assert "sk-vault-only" not in content


def test_redaction_strips_api_keys():
    from app.credentials.redaction import redact_text, redact_value

    text = redact_text("Error: api_key=sk-abcdefghijklmnopqrstuvwxyz123456")
    assert "sk-abc" not in text
    assert "REDACTED" in text
    data = redact_value({"api_key": "sk-secret", "detail": "failed with sk-1234567890abcdef"})
    assert data["api_key"] == "[REDACTED]"


def test_log_emit_event_redacts_secrets(isolated_paths):
    from app.core.observability import EventType, emit_event, trace_store

    before = len(trace_store.get_by_trace(""))
    emit_event(EventType.ERROR, {"api_key": "sk-leak-test", "detail": "Authorization: Bearer sk-abc123"})
    events = trace_store._events  # noqa: SLF001
    last = events[-1]
    assert last.data.get("api_key") == "[REDACTED]"
    assert "sk-leak" not in json.dumps(last.to_dict())
    assert before >= 0


def test_validate_only_does_not_persist(isolated_paths, master_key):
    from app.providers.connections.service import connection_service

    result = connection_service.create_connection(
        provider_type="openai",
        display_name="Draft",
        api_key="sk-draft",
        default_model="gpt-4o",
        validate_only=True,
    )
    assert "valid" in result
    assert connection_service.list_connections() == []


def test_env_fallback_without_master_key(tmp_path, monkeypatch):
    monkeypatch.delenv("BOETCLAW_MASTER_KEY", raising=False)
    vault_path = tmp_path / "credentials" / "vault.json"
    conn_path = tmp_path / "provider_connections.json"
    monkeypatch.setattr("app.credentials.vault.credential_vault._path", vault_path)
    monkeypatch.setattr("app.credentials.vault.credential_vault._loaded", False)
    monkeypatch.setattr("app.credentials.vault.credential_vault._records", {})
    monkeypatch.setattr("app.providers.connections.store.connection_store._path", conn_path)
    monkeypatch.setattr("app.providers.connections.store.connection_store._loaded", False)
    monkeypatch.setattr("app.providers.connections.store.connection_store._connections", {})
    monkeypatch.setattr("app.providers.connections.store.connection_store._default_connection_id", None)

    from app.core.config import settings
    from app.credentials.master_key import clear_master_key_cache
    from app.providers.connections.service import ConnectionServiceError, connection_service

    clear_master_key_cache()
    monkeypatch.setattr(settings, "openai_api_key", "sk-env-fallback", raising=False)
    with pytest.raises(ConnectionServiceError) as exc:
        connection_service.create_connection(
            provider_type="openai",
            display_name="Should fail",
            api_key="sk-new",
            default_model="gpt-4o",
        )
    assert exc.value.status_code == 503

    # Existing env provider still works via manager
    from app.providers.manager import provider_manager

    assert provider_manager.get("openai").is_configured() is True
