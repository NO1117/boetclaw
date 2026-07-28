"""Ollama (local model) provider."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ModelInfo, Provider
from app.providers.connections.runtime import get_runtime_config


class OllamaProvider(Provider):
    name = "ollama"
    display_name = "Ollama (Local)"
    requires_api_key = False
    default_model = "qwen2.5"

    def _base_url(self) -> str:
        runtime = get_runtime_config()
        if runtime and runtime.provider_type == self.name:
            return runtime.base_url or settings.ollama_base_url
        return settings.ollama_base_url

    def is_configured(self) -> bool:
        return bool(self._base_url())

    def get_chat_model(self, model: str, **kwargs: Any) -> Any:
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, base_url=self._base_url(), **kwargs)

    def list_models(self) -> list[ModelInfo]:
        """Query the local Ollama daemon for installed models."""
        models = self._fetch_installed()
        if models:
            return models
        return [ModelInfo(name=self.default_model, provider=self.name, metadata={"source": "default"})]

    def _fetch_installed(self) -> list[ModelInfo]:
        try:
            import httpx

            resp = httpx.get(f"{self._base_url()}/api/tags", timeout=2.0)
            resp.raise_for_status()
            data = resp.json()
            return [
                ModelInfo(name=m.get("name", ""), provider=self.name, metadata={"source": "ollama"})
                for m in data.get("models", [])
                if m.get("name")
            ]
        except Exception:
            return []

    def check_connection(self) -> dict[str, Any]:
        try:
            import httpx

            resp = httpx.get(f"{self._base_url()}/api/tags", timeout=2.0)
            connected = resp.status_code == 200
            return {"provider": self.name, "connected": connected, "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.name, "connected": False, "detail": str(exc)}
