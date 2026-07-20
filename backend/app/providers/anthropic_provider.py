"""Anthropic provider."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ModelInfo, Provider


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

    def is_configured(self) -> bool:
        return bool(settings.anthropic_api_key or settings.anthropic_base_url)

    def get_chat_model(self, model: str, **kwargs: Any) -> Any:
        from langchain_anthropic import ChatAnthropic

        init_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": settings.anthropic_api_key or ("not-needed" if settings.anthropic_base_url else None),
            **kwargs,
        }
        if settings.anthropic_base_url:
            init_kwargs["base_url"] = settings.anthropic_base_url
        return ChatAnthropic(**init_kwargs)

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(name=m, provider=self.name, context_window=cw, supports_vision=v)
            for m, cw, v in self._MODELS
        ]
