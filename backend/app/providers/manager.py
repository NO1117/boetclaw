"""Provider manager: registry + model_string resolution."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ModelInfo, Provider, ProviderInfo
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
        return [p.info() for p in self._providers.values()]

    @staticmethod
    def parse_model_string(model_string: str) -> tuple[str, str]:
        """Parse 'provider:model' -> (provider, model). Falls back to config default."""
        if ":" in model_string:
            provider, _, model = model_string.partition(":")
            return provider.strip(), model.strip()
        return settings.llm_provider, model_string.strip()

    def get_chat_model(self, model_string: str | None = None, **kwargs: Any) -> Any:
        model_string = model_string or settings.model_string
        provider_name, model = self.parse_model_string(model_string)
        provider = self.get(provider_name)
        emit_event(EventType.PROVIDER_RETRY, {"action": "resolve", "provider": provider_name, "model": model})
        provider_rate_limiter.check(provider_name, model)
        return provider.get_chat_model(model, **kwargs)

    def list_models(self, name: str) -> list[ModelInfo]:
        return self.get(name).list_models()

    def check_connection(self, name: str) -> dict[str, Any]:
        return self.get(name).check_connection()


provider_manager = ProviderManager()
