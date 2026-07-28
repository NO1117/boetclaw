"""Provider connection business logic."""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.config import settings
from app.core.observability import get_logger
from app.credentials.redaction import fingerprint_last4, redact_text
from app.credentials.vault import CredentialVaultError, credential_vault
from app.providers.connections.models import ConnectionCheckResult, ProviderConnection, _now_iso
from app.providers.connections.runtime import RuntimeConnectionConfig, runtime_connection
from app.providers.connections.store import ConnectionConflictError, ConnectionStoreError, connection_store
from app.providers.connections.url_validation import UrlValidationError, validate_base_url

logger = get_logger("connection_service")

PROVIDER_TYPES = frozenset({"openai", "anthropic", "ollama"})
REQUIRES_API_KEY = frozenset({"openai", "anthropic"})


def _manager():
    from app.providers.manager import provider_manager

    return provider_manager


class ConnectionServiceError(ValueError):
    def __init__(self, message: str, status_code: int = 400, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


class ConnectionReferenceError(ConnectionServiceError):
    def __init__(self, message: str, references: list[dict[str, str]]) -> None:
        super().__init__(message, 409, detail={"references": references})
        self.references = references


def _requires_api_key(provider_type: str) -> bool:
    return provider_type in REQUIRES_API_KEY


def _env_api_key(provider_type: str) -> str:
    if provider_type == "openai":
        return settings.openai_api_key
    if provider_type == "anthropic":
        return settings.anthropic_api_key
    return ""


def _env_base_url(provider_type: str) -> str:
    if provider_type == "openai":
        return settings.openai_base_url
    if provider_type == "anthropic":
        return settings.anthropic_base_url
    if provider_type == "ollama":
        return settings.ollama_base_url
    return ""


def _credential_source(conn: ProviderConnection) -> tuple[str, bool, str]:
    """Return (source, configured, fingerprint)."""
    if not _requires_api_key(conn.provider_type):
        return "none", True, ""
    if conn.credential_id:
        try:
            credential_vault.get_meta(conn.credential_id)
            dec = credential_vault.use_ephemeral(conn.credential_id)
            fp = fingerprint_last4(dec.api_key())
            return "vault", bool(dec.api_key()), fp
        except CredentialVaultError:
            return "vault", False, ""
    env_key = _env_api_key(conn.provider_type)
    if env_key:
        return "environment", True, fingerprint_last4(env_key)
    base = conn.base_url or _env_base_url(conn.provider_type)
    if base:
        return "environment", True, ""
    return "none", False, ""


def _public_connection(conn: ProviderConnection) -> dict[str, Any]:
    source, configured, fp = _credential_source(conn)
    return conn.to_public_dict(
        credential_source=source,  # type: ignore[arg-type]
        credential_configured=configured,
        credential_fingerprint=fp,
    )


def _resolve_runtime_config(conn: ProviderConnection) -> RuntimeConnectionConfig:
    base_url = conn.base_url or _env_base_url(conn.provider_type)
    api_key = ""
    if _requires_api_key(conn.provider_type):
        if conn.credential_id:
            dec = credential_vault.use_ephemeral(conn.credential_id)
            api_key = dec.api_key()
        else:
            api_key = _env_api_key(conn.provider_type)
    return RuntimeConnectionConfig(
        connection_id=conn.id,
        provider_type=conn.provider_type,
        base_url=base_url,
        api_key=api_key,
    )


class ConnectionService:
    def vault_status(self) -> dict[str, Any]:
        return credential_vault.status().to_dict()

    def list_connections(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        items = connection_store.list_all()
        if enabled_only:
            items = [c for c in items if c.enabled]
        return [_public_connection(c) for c in items]

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        return _public_connection(connection_store.get(connection_id))

    def get_default_connection(self) -> ProviderConnection | None:
        default_id = connection_store.get_default_id()
        if not default_id:
            return None
        try:
            return connection_store.get(default_id)
        except ConnectionStoreError:
            return None

    def resolve_connection_id(self, ref: str) -> str | None:
        """Resolve provider type name or connection id to connection id."""
        if not ref:
            return connection_store.get_default_id()
        if ref.startswith("conn_"):
            try:
                connection_store.get(ref)
                return ref
            except ConnectionStoreError:
                return None
        # Legacy provider type -> default enabled connection of that type
        for conn in connection_store.list_all():
            if conn.provider_type == ref and conn.enabled:
                return conn.id
        return None

    def create_connection(
        self,
        *,
        provider_type: str,
        display_name: str,
        base_url: str = "",
        api_key: str | None = None,
        default_model: str = "",
        enabled: bool = True,
        timeout_seconds: int = 30,
        set_default: bool = False,
        validate_only: bool = False,
    ) -> dict[str, Any]:
        provider_type = provider_type.strip().lower()
        if provider_type not in PROVIDER_TYPES:
            raise ConnectionServiceError(f"不支持的 Provider 类型: {provider_type}")
        try:
            base_url = validate_base_url(base_url)
        except UrlValidationError as exc:
            raise ConnectionServiceError(str(exc)) from exc

        provider = _manager().get(provider_type)
        if not default_model:
            default_model = provider.default_model

        credential_id: str | None = None
        if _requires_api_key(provider_type) and api_key and api_key.strip():
            if validate_only:
                draft = ProviderConnection(
                    id="draft",
                    provider_type=provider_type,
                    display_name=display_name,
                    base_url=base_url,
                    credential_id=None,
                    default_model=default_model,
                    enabled=enabled,
                    timeout_seconds=timeout_seconds,
                    revision=0,
                    created_at=_now_iso(),
                    updated_at=_now_iso(),
                )
                return self._validate_draft(draft, api_key=api_key.strip())

            try:
                meta = credential_vault.create(
                    purpose="provider_api_key",
                    payload={"api_key": api_key.strip()},
                    label=f"{provider_type}:{display_name}",
                )
                credential_id = meta.id
            except CredentialVaultError as exc:
                raise ConnectionServiceError(str(exc), exc.status_code) from exc

        if validate_only:
            draft = ProviderConnection(
                id="draft",
                provider_type=provider_type,
                display_name=display_name,
                base_url=base_url,
                credential_id=credential_id,
                default_model=default_model,
                enabled=enabled,
                timeout_seconds=timeout_seconds,
                revision=0,
                created_at=_now_iso(),
                updated_at=_now_iso(),
            )
            return self._validate_draft(draft, api_key=api_key.strip() if api_key else "")

        conn_id = f"conn_{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        conn = ProviderConnection(
            id=conn_id,
            provider_type=provider_type,
            display_name=display_name.strip() or provider.display_name,
            base_url=base_url,
            credential_id=credential_id,
            default_model=default_model,
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        saved = connection_store.upsert(conn, expected_revision=None)
        if credential_id:
            credential_vault.increment_ref(credential_id, 1)
        if set_default or connection_store.get_default_id() is None:
            connection_store.set_default_id(saved.id)
            saved = connection_store.get(saved.id)
        self._sync_legacy_settings(saved)
        self._invalidate_caches(saved)
        logger.info("connection_created", connection_id=saved.id, provider_type=provider_type)
        return _public_connection(saved)

    def update_connection(
        self,
        connection_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        enabled: bool | None = None,
        timeout_seconds: int | None = None,
        expected_revision: int | None = None,
        validate_only: bool = False,
    ) -> dict[str, Any]:
        conn = connection_store.get(connection_id)
        if display_name is not None:
            conn.display_name = display_name.strip()
        if base_url is not None:
            try:
                conn.base_url = validate_base_url(base_url)
            except UrlValidationError as exc:
                raise ConnectionServiceError(str(exc)) from exc
        if default_model is not None:
            conn.default_model = default_model.strip()
        if enabled is not None:
            conn.enabled = enabled
        if timeout_seconds is not None:
            conn.timeout_seconds = max(1, min(timeout_seconds, 300))

        new_api_key = api_key.strip() if api_key and api_key.strip() else None
        if new_api_key and _requires_api_key(conn.provider_type):
            if validate_only:
                return self._validate_draft(conn, api_key=new_api_key)
            if conn.credential_id:
                try:
                    credential_vault.replace(conn.credential_id, payload={"api_key": new_api_key})
                except CredentialVaultError as exc:
                    raise ConnectionServiceError(str(exc), exc.status_code) from exc
            else:
                try:
                    meta = credential_vault.create(
                        purpose="provider_api_key",
                        payload={"api_key": new_api_key},
                        label=f"{conn.provider_type}:{conn.display_name}",
                    )
                    conn.credential_id = meta.id
                    credential_vault.increment_ref(meta.id, 1)
                except CredentialVaultError as exc:
                    raise ConnectionServiceError(str(exc), exc.status_code) from exc

        if validate_only:
            return self._validate_draft(conn, api_key=new_api_key or "")

        old_cred = connection_store.get(connection_id).credential_id
        try:
            saved = connection_store.upsert(conn, expected_revision=expected_revision)
        except ConnectionConflictError as exc:
            raise ConnectionServiceError(str(exc), 409) from exc
        self._sync_legacy_settings(saved)
        self._invalidate_caches(saved)
        if old_cred != saved.credential_id and old_cred:
            self._maybe_release_credential(old_cred)
        logger.info("connection_updated", connection_id=connection_id)
        return _public_connection(saved)

    def clone_connection(self, connection_id: str) -> dict[str, Any]:
        src = connection_store.get(connection_id)
        api_key: str | None = None
        if src.credential_id and _requires_api_key(src.provider_type):
            dec = credential_vault.use_ephemeral(src.credential_id)
            api_key = dec.api_key()
        return self.create_connection(
            provider_type=src.provider_type,
            display_name=f"{src.display_name} (副本)",
            base_url=src.base_url,
            api_key=api_key,
            default_model=src.default_model,
            enabled=src.enabled,
            timeout_seconds=src.timeout_seconds,
        )

    def set_default(self, connection_id: str) -> dict[str, Any]:
        conn = connection_store.get(connection_id)
        if not conn.enabled:
            raise ConnectionServiceError("已禁用的连接不能设为默认")
        connection_store.set_default_id(connection_id)
        conn = connection_store.get(connection_id)
        self._sync_legacy_settings(conn)
        self._invalidate_caches(conn)
        return _public_connection(conn)

    def delete_connection(self, connection_id: str) -> None:
        refs = self._find_references(connection_id)
        if refs:
            raise ConnectionReferenceError("连接仍被引用，无法删除", refs)
        conn = connection_store.delete(connection_id)
        if conn.credential_id:
            self._maybe_release_credential(conn.credential_id)
        self._invalidate_caches(conn)
        logger.info("connection_deleted", connection_id=connection_id)

    def check_connection(
        self,
        connection_id: str,
        *,
        draft: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if draft:
            conn = ProviderConnection(
                id=connection_id,
                provider_type=str(draft.get("provider_type", "")),
                display_name=str(draft.get("display_name", "")),
                base_url=str(draft.get("base_url", "")),
                credential_id=draft.get("credential_id"),
                default_model=str(draft.get("default_model", "")),
                enabled=True,
                timeout_seconds=int(draft.get("timeout_seconds", 30) or 30),
                revision=0,
                created_at=_now_iso(),
                updated_at=_now_iso(),
            )
            api_key = str(draft.get("api_key") or "")
        else:
            conn = connection_store.get(connection_id)
            api_key = ""

        started = time.perf_counter()
        try:
            runtime = _resolve_runtime_config(conn)
            if draft and api_key:
                runtime = RuntimeConnectionConfig(
                    connection_id=conn.id,
                    provider_type=conn.provider_type,
                    base_url=conn.base_url or _env_base_url(conn.provider_type),
                    api_key=api_key,
                )
            with runtime_connection(runtime):
                provider = _manager().get(conn.provider_type)
                if not provider.is_configured():
                    result = ConnectionCheckResult(
                        connected=False,
                        detail="未配置凭据或 Base URL",
                        error_category="not_configured",
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                else:
                    raw = provider.check_connection()
                    models = provider.list_models()
                    result = ConnectionCheckResult(
                        connected=bool(raw.get("connected")),
                        detail=redact_text(str(raw.get("detail", "")))[:200],
                        error_category="" if raw.get("connected") else "upstream_error",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        model_count=len(models),
                    )
        except CredentialVaultError as exc:
            result = ConnectionCheckResult(
                connected=False,
                detail=redact_text(str(exc)),
                error_category="vault_error",
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:  # noqa: BLE001
            result = ConnectionCheckResult(
                connected=False,
                detail=redact_text(str(exc))[:200],
                error_category="internal_error",
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        if not draft and connection_id in {c.id for c in connection_store.list_all()}:
            conn = connection_store.get(connection_id)
            conn.last_check = result
            connection_store.upsert(conn, expected_revision=conn.revision)

        out = result.to_public_dict()
        out["connection_id"] = connection_id
        out["provider_type"] = conn.provider_type
        return out

    def import_from_env(self) -> dict[str, Any]:
        imported: list[str] = []
        for provider_type in ("openai", "anthropic"):
            key = _env_api_key(provider_type)
            if not key:
                continue
            existing = [
                c for c in connection_store.list_all()
                if c.provider_type == provider_type and c.credential_id
            ]
            if existing:
                continue
            base = _env_base_url(provider_type)
            provider = _manager().get(provider_type)
            conn = self.create_connection(
                provider_type=provider_type,
                display_name=f"{provider.display_name} (环境变量导入)",
                base_url=base,
                api_key=key,
                default_model=provider.default_model,
                set_default=(settings.llm_provider == provider_type and connection_store.get_default_id() is None),
            )
            imported.append(conn["id"])

        # Ollama: no credential, just base URL connection
        if settings.ollama_base_url:
            ollama_existing = [c for c in connection_store.list_all() if c.provider_type == "ollama"]
            if not ollama_existing:
                provider = _manager().get("ollama")
                conn = self.create_connection(
                    provider_type="ollama",
                    display_name=f"{provider.display_name} (环境变量导入)",
                    base_url=settings.ollama_base_url,
                    default_model=settings.llm_model if settings.llm_provider == "ollama" else provider.default_model,
                    set_default=(settings.llm_provider == "ollama" and connection_store.get_default_id() is None),
                )
                imported.append(conn["id"])

        return {
            "imported_connection_ids": imported,
            "count": len(imported),
            "env_cleanup_required": bool(imported),
            "message": (
                "已从环境变量导入凭据到保险箱。"
                "请手动清理 .env 中的 API Key 明文；系统不会自动删除。"
                if imported
                else "未发现可导入的环境变量凭据，或对应连接已存在。"
            ),
        }

    def migrate_from_settings_if_empty(self) -> None:
        if connection_store.path.exists():
            connection_store.list_all()
            if connection_store.list_all():
                return
        for provider_type in ("openai", "anthropic", "ollama"):
            key = _env_api_key(provider_type)
            base = _env_base_url(provider_type)
            if not key and not base:
                continue
            provider = _manager().get(provider_type)
            try:
                self.create_connection(
                    provider_type=provider_type,
                    display_name=f"{provider.display_name} (默认)",
                    base_url=base,
                    api_key=key or None,
                    default_model=provider.default_model,
                    set_default=(settings.llm_provider == provider_type),
                )
            except (ConnectionServiceError, CredentialVaultError):
                # No master key: create connection without vault credential
                if provider_type == "ollama" or base:
                    now = _now_iso()
                    conn_id = f"conn_{uuid.uuid4().hex[:16]}"
                    conn = ProviderConnection(
                        id=conn_id,
                        provider_type=provider_type,
                        display_name=f"{provider.display_name} (默认)",
                        base_url=base,
                        credential_id=None,
                        default_model=provider.default_model,
                        enabled=True,
                        timeout_seconds=30,
                        revision=1,
                        created_at=now,
                        updated_at=now,
                    )
                    connection_store.upsert(conn, expected_revision=None)
                    if settings.llm_provider == provider_type:
                        connection_store.set_default_id(conn_id)

        default = self.get_default_connection()
        if default:
            self._sync_legacy_settings(default)

    def resolve_model_string(self, model_string: str) -> tuple[str, str, str, RuntimeConnectionConfig | None]:
        """Parse model string -> (connection_id|provider_type, model, model_string, runtime_config)."""
        if ":" not in model_string:
            default = self.get_default_connection()
            if default:
                model = model_string.strip() or default.default_model
                runtime = _resolve_runtime_config(default)
                return default.id, model, f"{default.id}:{model}", runtime
            prov, model = _manager().parse_model_string(model_string)
            return prov, model, f"{prov}:{model}", None

        head, _, model = model_string.partition(":")
        head = head.strip()
        model = model.strip()

        if head.startswith("conn_"):
            conn = connection_store.get(head)
            runtime = _resolve_runtime_config(conn)
            return head, model, f"{head}:{model}", runtime

        # Legacy provider:type
        conn_id = self.resolve_connection_id(head)
        if conn_id:
            conn = connection_store.get(conn_id)
            runtime = _resolve_runtime_config(conn)
            return conn_id, model, f"{conn_id}:{model}", runtime
        return head, model, f"{head}:{model}", None

    def _validate_draft(self, conn: ProviderConnection, *, api_key: str = "") -> dict[str, Any]:
        runtime = _resolve_runtime_config(conn)
        if api_key:
            runtime = RuntimeConnectionConfig(
                connection_id=conn.id,
                provider_type=conn.provider_type,
                base_url=conn.base_url or _env_base_url(conn.provider_type),
                api_key=api_key,
            )
        with runtime_connection(runtime):
            provider = _manager().get(conn.provider_type)
            valid = provider.is_configured()
        return {"valid": valid, "connection": _public_connection(conn)}

    def _find_references(self, connection_id: str) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        default_id = connection_store.get_default_id()
        if default_id == connection_id:
            refs.append({"kind": "default_connection", "id": connection_id})
        try:
            from app.agents.profile.service import profile_service
            from app.agents.multi_agent_manager import multi_agent_manager

            for workspace in multi_agent_manager.list_agents():
                agent_id = workspace.agent_id
                try:
                    profile = profile_service.get_or_create(agent_id)
                    resolved = self.resolve_connection_id(profile.provider.strip())
                    if resolved == connection_id:
                        refs.append({"kind": "agent_profile", "id": agent_id})
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return refs

    def _maybe_release_credential(self, credential_id: str) -> None:
        still_used = any(c.credential_id == credential_id for c in connection_store.list_all())
        if still_used:
            return
        try:
            credential_vault.increment_ref(credential_id, -1)
            meta = credential_vault.get_meta(credential_id)
            if meta.ref_count <= 0:
                credential_vault.delete(credential_id)
        except CredentialVaultError:
            pass

    def _sync_legacy_settings(self, conn: ProviderConnection) -> None:
        if connection_store.get_default_id() != conn.id:
            return
        settings.llm_provider = conn.provider_type
        settings.llm_model = conn.default_model

    def _invalidate_caches(self, conn: ProviderConnection) -> None:
        from app.agents.graph_cache import get_graph_cache

        cache = get_graph_cache()
        cache.invalidate_provider(conn.provider_type)
        if hasattr(cache, "invalidate_connection"):
            cache.invalidate_connection(conn.id)


connection_service = ConnectionService()
