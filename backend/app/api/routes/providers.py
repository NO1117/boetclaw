"""Provider management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.credentials.vault import CredentialVaultError
from app.providers.connections.service import ConnectionServiceError, connection_service
from app.providers.manager import provider_manager

router = APIRouter(prefix="/providers", tags=["Providers"])


class ProviderConfigUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


class DefaultProviderUpdate(BaseModel):
    provider: str
    model: str


def _legacy_provider_config(name: str) -> dict:
    provider_manager.get(name)
    conn_id = connection_service.resolve_connection_id(name)
    if conn_id:
        conn = connection_service.get_connection(conn_id)
        return {
            "name": name,
            "connection_id": conn_id,
            "api_key_configured": conn.get("credential_configured", False),
            "credential_source": conn.get("credential_source", "none"),
            "credential_fingerprint": conn.get("credential_fingerprint", ""),
            "base_url": conn.get("base_url", ""),
            "is_default": conn.get("is_default", False),
            "default_model": conn.get("default_model", provider_manager.get(name).default_model),
        }
    api_key = ""
    base_url = ""
    if name == "openai":
        api_key = settings.openai_api_key
        base_url = settings.openai_base_url
    elif name == "anthropic":
        api_key = settings.anthropic_api_key
        base_url = settings.anthropic_base_url
    elif name == "ollama":
        base_url = settings.ollama_base_url
    default = connection_service.get_default_connection()
    is_default = default is not None and default.provider_type == name if default else settings.llm_provider == name
    return {
        "name": name,
        "connection_id": None,
        "api_key_configured": bool(api_key) or bool(base_url and name != "ollama") or (name == "ollama" and bool(base_url)),
        "credential_source": "environment" if api_key else ("environment" if base_url else "none"),
        "credential_fingerprint": "",
        "base_url": base_url,
        "is_default": is_default,
        "default_model": (
            default.default_model if default and default.provider_type == name
            else (settings.llm_model if settings.llm_provider == name else provider_manager.get(name).default_model)
        ),
    }


@router.get("")
async def list_providers():
    return {"providers": [p.to_dict() for p in provider_manager.list_providers()]}


@router.get("/config")
async def get_default_config():
    default = connection_service.get_default_connection()
    if default:
        return {
            "provider": default.provider_type,
            "model": default.default_model,
            "connection_id": default.id,
        }
    return {"provider": settings.llm_provider, "model": settings.llm_model, "connection_id": None}


@router.put("/default")
async def update_default_provider(body: DefaultProviderUpdate):
    try:
        provider_manager.get(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    conn_id = connection_service.resolve_connection_id(body.provider)
    if conn_id:
        try:
            conn = connection_service.update_connection(
                conn_id,
                default_model=body.model,
                expected_revision=connection_service.get_connection(conn_id).get("revision"),
            )
            connection_service.set_default(conn_id)
            from app.agents.graph_cache import get_graph_cache

            get_graph_cache().invalidate_all()
            return {"provider": body.provider, "model": body.model, "connection_id": conn_id}
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ConnectionServiceError):
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
            raise

    settings.llm_provider = body.provider
    settings.llm_model = body.model
    from app.agents.graph_cache import get_graph_cache

    get_graph_cache().invalidate_all()
    return {"provider": settings.llm_provider, "model": settings.llm_model, "connection_id": None}


@router.get("/{name}/config")
async def get_provider_config(name: str):
    try:
        return _legacy_provider_config(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{name}/config")
async def update_provider_config(name: str, body: ProviderConfigUpdate):
    """Legacy route: persists API keys to vault via connection, never writes .env."""
    try:
        provider_manager.get(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    conn_id = connection_service.resolve_connection_id(name)
    try:
        if conn_id:
            rev = connection_service.get_connection(conn_id).get("revision")
            connection_service.update_connection(
                conn_id,
                base_url=body.base_url,
                api_key=body.api_key,
                expected_revision=rev,
            )
        else:
            connection_service.create_connection(
                provider_type=name,
                display_name=f"{name} (legacy)",
                base_url=body.base_url or "",
                api_key=body.api_key,
                set_default=(settings.llm_provider == name),
            )
        if body.base_url is not None:
            if name == "openai":
                settings.openai_base_url = body.base_url
            elif name == "anthropic":
                settings.anthropic_base_url = body.base_url
            elif name == "ollama":
                settings.ollama_base_url = body.base_url
        if body.api_key is not None and name in {"openai", "anthropic"}:
            if name == "openai":
                settings.openai_api_key = body.api_key
            else:
                settings.anthropic_api_key = body.api_key
    except CredentialVaultError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ConnectionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    from app.agents.graph_cache import get_graph_cache

    get_graph_cache().invalidate_provider(name)
    return _legacy_provider_config(name)


@router.get("/{name}/models")
async def list_models(name: str):
    try:
        return {"models": provider_manager.list_enriched_models(name)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{name}/check")
async def check_connection(name: str):
    try:
        return provider_manager.check_connection(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
