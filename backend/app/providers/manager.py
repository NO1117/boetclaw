"""Provider manager: registry + model_string resolution."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ModelInfo, Provider, ProviderInfo
from app.providers.connections.runtime import runtime_connection
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.rate_limiter import provider_rate_limiter

logger = get_logger("provider_manager")


class ProviderManager:
    """Singleton registry of model providers."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self.register(OpenAIProvider())
        self.register(AnthropicProvider())
        self.register(OllamaProvider())

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider:
        if name not in self._providers:
            raise ValueError(f"未知 provider: {name}")
        return self._providers[name]

    def list_providers(self) -> list[ProviderInfo]:
        from app.providers.connections.service import connection_service

        infos = [p.info() for p in self._providers.values()]
        enabled = [c for c in connection_service.list_connections() if c.get("enabled")]
        configured_types = {c["provider_type"] for c in enabled if c.get("credential_configured") or c["provider_type"] == "ollama"}
        for info in infos:
            if info.name in configured_types:
                info.configured = True
            default = connection_service.get_default_connection()
            if default and default.provider_type == info.name:
                info.default_model = default.default_model
        return infos

    @staticmethod
    def parse_model_string(model_string: str) -> tuple[str, str]:
        """Parse 'provider:model' or 'conn_xxx:model' -> (provider_or_conn, model)."""
        if ":" in model_string:
            provider, _, model = model_string.partition(":")
            return provider.strip(), model.strip()
        return settings.llm_provider, model_string.strip()

    def get_chat_model(self, model_string: str | None = None, **kwargs: Any) -> Any:
        from app.providers.connections.service import connection_service

        model_string = model_string or settings.model_string
        conn_ref, model, resolved, runtime = connection_service.resolve_model_string(model_string)
        provider_name = runtime.provider_type if runtime else conn_ref
        if runtime is None and conn_ref.startswith("conn_"):
            conn = connection_service.get_connection(conn_ref)
            provider_name = str(conn["provider_type"])
        elif not runtime:
            provider_name = conn_ref

        provider = self.get(provider_name)
        emit_event(EventType.PROVIDER_RETRY, {"action": "resolve", "provider": provider_name, "model": model})
        provider_rate_limiter.check(provider_name, model)

        if runtime:
            with runtime_connection(runtime):
                return provider.get_chat_model(model, **kwargs)
        return provider.get_chat_model(model, **kwargs)

    def list_models(self, name: str) -> list[ModelInfo]:
        return self.get(name).list_models()

    def list_enriched_models(self, name: str) -> list[dict]:
        return [m.to_dict() for m in self.get(name).list_enriched_models()]

    def list_models_for_connection(self, connection_id: str) -> list[dict]:
        from app.providers.connections.service import connection_service

        conn = connection_service.get_connection(connection_id)
        provider_type = str(conn["provider_type"])
        _, _, _, runtime = connection_service.resolve_model_string(f"{connection_id}:{conn['default_model']}")
        if runtime:
            with runtime_connection(runtime):
                return self.list_enriched_models(provider_type)
        return self.list_enriched_models(provider_type)

    def check_connection(self, name: str) -> dict[str, Any]:
        from app.providers.connections.service import connection_service

        conn_id = connection_service.resolve_connection_id(name)
        if conn_id:
            return connection_service.check_connection(conn_id)
        return self.get(name).check_connection()


provider_manager = ProviderManager()
