"""Provider abstraction base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelInfo:
    name: str
    provider: str
    context_window: int = 0
    supports_tools: bool = True
    supports_vision: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "context_window": self.context_window,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "metadata": self.metadata,
        }


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
