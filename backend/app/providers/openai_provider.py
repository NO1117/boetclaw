"""OpenAI provider."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ModelInfo, Provider


class OpenAIProvider(Provider):
    name = "openai"
    display_name = "OpenAI"
    requires_api_key = True
    default_model = "gpt-4o"

    _MODELS = [
        ("gpt-4o", 128000, True),
        ("gpt-4o-mini", 128000, True),
        ("gpt-4-turbo", 128000, True),
        ("o1", 200000, False),
    ]

    def _model_info(self, name: str, cw: int, vision: bool) -> ModelInfo:
        return ModelInfo(
            name=name,
            provider=self.name,
            context_window=cw,
            supports_vision=vision,
            supports_tools=True,
        )

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key or settings.openai_base_url)

    def get_chat_model(self, model: str, **kwargs: Any) -> Any:
        from langchain_openai import ChatOpenAI

        init_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": settings.openai_api_key or ("not-needed" if settings.openai_base_url else None),
            **kwargs,
        }
        if settings.openai_base_url:
            init_kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**init_kwargs)

    def list_models(self) -> list[ModelInfo]:
        return [self._model_info(m, cw, v) for m, cw, v in self._MODELS]
