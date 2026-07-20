"""Provider management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import BASE_DIR
from app.core.config import settings
from app.core.env_file import update_env_file
from app.providers.manager import provider_manager

router = APIRouter(prefix="/providers", tags=["Providers"])
PROVIDER_ENV_PATH = BASE_DIR / ".env"


class ProviderConfigUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


class DefaultProviderUpdate(BaseModel):
    provider: str
    model: str


def _provider_config(name: str) -> dict:
    provider_manager.get(name)
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
    return {
        "name": name,
        "api_key_configured": bool(api_key),
        "base_url": base_url,
        "is_default": settings.llm_provider == name,
        "default_model": settings.llm_model if settings.llm_provider == name else provider_manager.get(name).default_model,
    }


@router.get("")
async def list_providers():
    return {"providers": [p.to_dict() for p in provider_manager.list_providers()]}


@router.get("/config")
async def get_default_config():
    return {"provider": settings.llm_provider, "model": settings.llm_model}


@router.put("/default")
async def update_default_provider(body: DefaultProviderUpdate):
    try:
        provider_manager.get(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    settings.llm_provider = body.provider
    settings.llm_model = body.model
    update_env_file({"LLM_PROVIDER": body.provider, "LLM_MODEL": body.model}, PROVIDER_ENV_PATH)
    return {"provider": settings.llm_provider, "model": settings.llm_model}


@router.get("/{name}/config")
async def get_provider_config(name: str):
    try:
        return _provider_config(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{name}/config")
async def update_provider_config(name: str, body: ProviderConfigUpdate):
    try:
        provider_manager.get(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if name == "openai":
        env_updates = {}
        if body.api_key is not None:
            settings.openai_api_key = body.api_key
            env_updates["OPENAI_API_KEY"] = body.api_key
        if body.base_url is not None:
            settings.openai_base_url = body.base_url
            env_updates["OPENAI_BASE_URL"] = body.base_url
        if env_updates:
            update_env_file(env_updates, PROVIDER_ENV_PATH)
    elif name == "anthropic":
        env_updates = {}
        if body.api_key is not None:
            settings.anthropic_api_key = body.api_key
            env_updates["ANTHROPIC_API_KEY"] = body.api_key
        if body.base_url is not None:
            settings.anthropic_base_url = body.base_url
            env_updates["ANTHROPIC_BASE_URL"] = body.base_url
        if env_updates:
            update_env_file(env_updates, PROVIDER_ENV_PATH)
    elif name == "ollama":
        if body.base_url is not None:
            settings.ollama_base_url = body.base_url
            update_env_file({"OLLAMA_BASE_URL": body.base_url}, PROVIDER_ENV_PATH)
    return _provider_config(name)


@router.get("/{name}/models")
async def list_models(name: str):
    try:
        return {"models": [m.to_dict() for m in provider_manager.list_models(name)]}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{name}/check")
async def check_connection(name: str):
    try:
        return provider_manager.check_connection(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
