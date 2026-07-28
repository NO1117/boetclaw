"""Provider connection management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.credentials.vault import CredentialVaultError
from app.identity.actor import require_permission
from app.identity.permissions import PROVIDERS_CREDENTIALS, PROVIDERS_MANAGE
from app.providers.connections.service import (
    ConnectionConflictError,
    ConnectionReferenceError,
    ConnectionServiceError,
    connection_service,
)
from app.providers.connections.store import ConnectionStoreError
from app.providers.manager import provider_manager

router = APIRouter(prefix="/provider-connections", tags=["Provider Connections"])


class ConnectionCreate(BaseModel):
    provider_type: str
    display_name: str = ""
    base_url: str = ""
    api_key: str | None = None
    default_model: str = ""
    enabled: bool = True
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    set_default: bool = False
    validate_only: bool = False


class ConnectionUpdate(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    expected_revision: int | None = None
    validate_only: bool = False


class ConnectionCheckDraft(BaseModel):
    provider_type: str | None = None
    display_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    timeout_seconds: int | None = None
    credential_id: str | None = None


class VaultRotateRequest(BaseModel):
    new_master_key: str


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ConnectionServiceError, ConnectionStoreError, CredentialVaultError)):
        detail: str | dict = exc.detail if isinstance(exc, ConnectionServiceError) and exc.detail else str(exc)
        return HTTPException(status_code=getattr(exc, "status_code", 400), detail=detail)
    if isinstance(exc, ConnectionConflictError):
        return HTTPException(
            status_code=409,
            detail={"message": str(exc), "expected_revision": exc.expected_revision, "actual_revision": exc.actual_revision},
        )
    if isinstance(exc, ConnectionReferenceError):
        return HTTPException(status_code=409, detail={"message": str(exc), "references": exc.references})
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/vault/status")
async def vault_status(request: Request):
    require_permission(request, PROVIDERS_MANAGE)
    return connection_service.vault_status()


@router.get("")
async def list_connections(request: Request, enabled_only: bool = Query(default=False)):
    from app.identity.actor import require_actor

    actor = require_actor(request)
    rows = connection_service.list_connections(enabled_only=enabled_only)
    if actor.has(PROVIDERS_MANAGE) or actor.role in {"owner", "admin"} or actor.actor_type in {
        "open",
        "api_token",
        "console_legacy",
    }:
        return {"connections": rows}
    # Non-admins see redacted selectable names only
    redacted = [
        {
            "id": c.get("id"),
            "display_name": c.get("display_name"),
            "provider_type": c.get("provider_type"),
            "default_model": c.get("default_model"),
            "enabled": c.get("enabled"),
            "is_default": c.get("is_default"),
            "credential_configured": bool(c.get("credential_configured")),
        }
        for c in rows
        if c.get("enabled", True)
    ]
    return {"connections": redacted}


@router.post("")
async def create_connection(body: ConnectionCreate, request: Request):
    require_permission(request, PROVIDERS_MANAGE)
    try:
        conn = connection_service.create_connection(
            provider_type=body.provider_type,
            display_name=body.display_name,
            base_url=body.base_url,
            api_key=body.api_key,
            default_model=body.default_model,
            enabled=body.enabled,
            timeout_seconds=body.timeout_seconds,
            set_default=body.set_default,
            validate_only=body.validate_only,
        )
        if body.validate_only:
            return conn
        return {"connection": conn}
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/import-env")
async def import_env_credentials(request: Request):
    require_permission(request, PROVIDERS_MANAGE)
    try:
        return connection_service.import_from_env()
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/{connection_id}")
async def get_connection(connection_id: str):
    try:
        return {"connection": connection_service.get_connection(connection_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.put("/{connection_id}")
async def update_connection(connection_id: str, body: ConnectionUpdate, request: Request):
    require_permission(request, PROVIDERS_MANAGE)
    try:
        conn = connection_service.update_connection(
            connection_id,
            display_name=body.display_name,
            base_url=body.base_url,
            api_key=body.api_key,
            default_model=body.default_model,
            enabled=body.enabled,
            timeout_seconds=body.timeout_seconds,
            expected_revision=body.expected_revision,
            validate_only=body.validate_only,
        )
        if body.validate_only:
            return conn
        return {"connection": conn}
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str, request: Request):
    require_permission(request, PROVIDERS_MANAGE)
    try:
        connection_service.delete_connection(connection_id)
        return {"deleted": True, "connection_id": connection_id}
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/{connection_id}/check")
async def check_connection(connection_id: str, body: ConnectionCheckDraft | None = None):
    try:
        draft = body.model_dump(exclude_none=True) if body else None
        return connection_service.check_connection(connection_id, draft=draft)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/{connection_id}/set-default")
async def set_default_connection(connection_id: str):
    try:
        return {"connection": connection_service.set_default(connection_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.post("/{connection_id}/clone")
async def clone_connection(connection_id: str):
    try:
        return {"connection": connection_service.clone_connection(connection_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc


@router.get("/{connection_id}/models")
async def list_connection_models(connection_id: str):
    try:
        connection_service.get_connection(connection_id)
        return {"models": provider_manager.list_models_for_connection(connection_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
