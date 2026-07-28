"""Anthropic provider."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ModelInfo, Provider
from app.providers.connections.runtime import get_runtime_config


class AnthropicProvider(Provider):
    name = "anthropic"
    display_name = "Anthropic"
    requires_api_key = True
    default_model = "claude-3-5-sonnet-latest"

    _MODELS = [
        ("claude-3-5-sonnet-latest", 200000, True),
        ("claude-3-5-haiku-latest", 200000, False),
        ("claude-3-opus-latest", 200000, True),
    ]

    def _credentials(self) -> tuple[str, str]:
        runtime = get_runtime_config()
        if runtime and runtime.provider_type == self.name:
            return runtime.api_key, runtime.base_url
        return settings.anthropic_api_key, settings.anthropic_base_url

    def is_configured(self) -> bool:
        api_key, base_url = self._credentials()
        return bool(api_key or base_url)

    def get_chat_model(self, model: str, **kwargs: Any) -> Any:
        from langchain_anthropic import ChatAnthropic

        api_key, base_url = self._credentials()
        init_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": api_key or ("not-needed" if base_url else None),
            **kwargs,
        }
        if base_url:
            init_kwargs["base_url"] = base_url
        return ChatAnthropic(**init_kwargs)

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(name=m, provider=self.name, context_window=cw, supports_vision=v)
            for m, cw, v in self._MODELS
        ]
