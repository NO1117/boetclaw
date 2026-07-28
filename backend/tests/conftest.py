"""Shared pytest fixtures."""

from __future__ import annotations

import base64
import os

import pytest


def _master_key_b64() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


@pytest.fixture
def master_key(monkeypatch):
    key = _master_key_b64()
    monkeypatch.setenv("BOETCLAW_MASTER_KEY", key)
    from app.credentials.master_key import clear_master_key_cache

    clear_master_key_cache()
    yield key
    clear_master_key_cache()


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


@pytest.fixture(autouse=True)
def isolated_identity(tmp_path, monkeypatch):
    """Keep identity SQLite out of shared workspace/ for every test."""
    from app.identity.service import identity_service
    from app.identity.store import IdentityStore

    db_path = tmp_path / "identity-test" / "identity.sqlite3"
    monkeypatch.setattr("app.core.config.settings.identity_sqlite_path", db_path, raising=False)
    identity_service.close()
    identity_service.store = IdentityStore(db_path=db_path)
    identity_service._initialized = False
    yield
    identity_service.close()
