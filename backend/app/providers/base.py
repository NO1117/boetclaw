"""Provider abstraction base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.providers.capabilities import EnrichedModelInfo, ModelCapabilities, enrich_model


@dataclass
class ModelInfo:
    name: str
    provider: str
    context_window: int = 0
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def enriched(self) -> EnrichedModelInfo:
        caps = ModelCapabilities(
            vision=self.supports_vision,
            tools=self.supports_tools if self.supports_tools is not None else None,
        )
        return enrich_model(
            name=self.name,
            provider=self.provider,
            context_window=self.context_window or None,
            max_output_tokens=self.max_output_tokens,
            capabilities=caps,
            metadata=self.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.enriched().to_dict()


@dataclass
class ProviderInfo:
    name: str
    display_name: str
    configured: bool
    default_model: str
    requires_api_key: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "configured": self.configured,
            "default_model": self.default_model,
            "requires_api_key": self.requires_api_key,
        }


class Provider(ABC):
    """Abstract model provider."""

    name: str = "base"
    display_name: str = "Base"
    requires_api_key: bool = True
    default_model: str = ""

    @abstractmethod
    def get_chat_model(self, model: str, **kwargs: Any) -> Any:
        """Return a LangChain chat model instance."""

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """List available models for this provider."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the provider has required credentials/endpoint."""

    def check_connection(self) -> dict[str, Any]:
        """Best-effort connectivity check. Override for real probing."""
        return {"provider": self.name, "connected": self.is_configured(), "detail": "config-only"}

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            display_name=self.display_name,
            configured=self.is_configured(),
            default_model=self.default_model,
            requires_api_key=self.requires_api_key,
        )

    def list_enriched_models(self) -> list[EnrichedModelInfo]:
        return [m.enriched() for m in self.list_models()]
