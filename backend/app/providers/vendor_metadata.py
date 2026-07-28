"""Static vendor model capability declarations and optional pricing."""

from __future__ import annotations

from typing import Any

# Prices are optional estimates in USD per 1M tokens; null when unknown.
_STATIC: dict[str, dict[str, dict[str, Any]]] = {
    "openai": {
        "gpt-4o": {
            "context_window": 128_000,
            "max_output_tokens": 16_384,
            "vision": True,
            "tools": True,
            "audio_input": False,
            "audio_output": False,
            "structured_output": True,
            "is_local": False,
            "input_price_per_million": 2.50,
            "output_price_per_million": 10.00,
        },
        "gpt-4o-mini": {
            "context_window": 128_000,
            "max_output_tokens": 16_384,
            "vision": True,
            "tools": True,
            "structured_output": True,
            "is_local": False,
            "input_price_per_million": 0.15,
            "output_price_per_million": 0.60,
        },
        "gpt-4-turbo": {
            "context_window": 128_000,
            "max_output_tokens": 4096,
            "vision": True,
            "tools": True,
            "structured_output": True,
            "is_local": False,
        },
        "o1": {
            "context_window": 200_000,
            "max_output_tokens": 100_000,
            "vision": False,
            "tools": False,
            "structured_output": True,
            "is_local": False,
        },
    },
    "anthropic": {
        "claude-3-5-sonnet-latest": {
            "context_window": 200_000,
            "max_output_tokens": 8192,
            "vision": True,
            "tools": True,
            "structured_output": True,
            "is_local": False,
            "input_price_per_million": 3.00,
            "output_price_per_million": 15.00,
        },
        "claude-3-5-haiku-latest": {
            "context_window": 200_000,
            "max_output_tokens": 8192,
            "vision": False,
            "tools": True,
            "structured_output": True,
            "is_local": False,
        },
        "claude-3-opus-latest": {
            "context_window": 200_000,
            "max_output_tokens": 4096,
            "vision": True,
            "tools": True,
            "structured_output": True,
            "is_local": False,
        },
    },
    "ollama": {
        "*": {
            "is_local": True,
            "tools": None,
            "vision": None,
        },
    },
}


def get_static_model_metadata(provider: str, model: str) -> dict[str, Any]:
    provider_map = _STATIC.get(provider, {})
    if model in provider_map:
        return dict(provider_map[model])
    if "*" in provider_map:
        return dict(provider_map["*"])
    return {}
