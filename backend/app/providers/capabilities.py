"""Tri-state model capabilities and static/dynamic merge."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from app.providers.capability_cache import get_capability_cache
from app.providers.vendor_metadata import get_static_model_metadata

CapabilityTriState = Literal["true", "false", "unknown"]
CapabilitySource = Literal["static", "dynamic", "merged"]


def _tri(v: bool | None) -> CapabilityTriState:
    if v is True:
        return "true"
    if v is False:
        return "false"
    return "unknown"


def _parse_tri(raw: Any) -> bool | None:
    if raw is True or raw == "true":
        return True
    if raw is False or raw == "false":
        return False
    return None


@dataclass
class ModelCapabilities:
    vision: bool | None = None
    tools: bool | None = None
    audio_input: bool | None = None
    audio_output: bool | None = None
    structured_output: bool | None = None
    is_local: bool | None = None

    def to_dict(self) -> dict[str, CapabilityTriState]:
        return {
            "vision": _tri(self.vision),
            "tools": _tri(self.tools),
            "audio_input": _tri(self.audio_input),
            "audio_output": _tri(self.audio_output),
            "structured_output": _tri(self.structured_output),
            "is_local": _tri(self.is_local),
        }

    def merge_dynamic(self, other: ModelCapabilities) -> ModelCapabilities:
        """Dynamic probe wins over static when known."""

        def pick(a: bool | None, b: bool | None) -> bool | None:
            return b if b is not None else a

        return ModelCapabilities(
            vision=pick(self.vision, other.vision),
            tools=pick(self.tools, other.tools),
            audio_input=pick(self.audio_input, other.audio_input),
            audio_output=pick(self.audio_output, other.audio_output),
            structured_output=pick(self.structured_output, other.structured_output),
            is_local=pick(self.is_local, other.is_local),
        )


@dataclass
class EnrichedModelInfo:
    name: str
    provider: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    capability_sources: dict[str, CapabilitySource] = field(default_factory=dict)
    capability_updated_at: dict[str, str] = field(default_factory=dict)
    pricing: dict[str, float | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def supports_vision(self) -> bool | None:
        return self.capabilities.vision

    @property
    def supports_tools(self) -> bool | None:
        return self.capabilities.tools

    def to_dict(self) -> dict[str, Any]:
        caps = self.capabilities.to_dict()
        out: dict[str, Any] = {
            "name": self.name,
            "provider": self.provider,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "capabilities": caps,
            "capability_sources": dict(self.capability_sources),
            "capability_updated_at": dict(self.capability_updated_at),
            "pricing": self.pricing,
            "metadata": self.metadata,
            # Backward-compatible booleans: null when unknown
            "supports_vision": self.capabilities.vision,
            "supports_tools": self.capabilities.tools,
        }
        return out


def _load_dynamic_caps(model_key: str) -> tuple[ModelCapabilities, dict[str, str], dict[str, str]]:
    cache = get_capability_cache()
    entry = cache.all().get(model_key, {})
    caps_raw = entry.get("capabilities", {})
    sources_raw = entry.get("sources", {})
    updated_raw = entry.get("updated_at", {})
    caps = ModelCapabilities(
        vision=_parse_tri(caps_raw.get("vision")),
        tools=_parse_tri(caps_raw.get("tools")),
        audio_input=_parse_tri(caps_raw.get("audio_input")),
        audio_output=_parse_tri(caps_raw.get("audio_output")),
        structured_output=_parse_tri(caps_raw.get("structured_output")),
        is_local=_parse_tri(caps_raw.get("is_local")),
    )
    sources = {k: "dynamic" for k in sources_raw}
    updated = {k: str(v) for k, v in updated_raw.items()}
    return caps, sources, updated


def enrich_model(
    *,
    name: str,
    provider: str,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
    capabilities: ModelCapabilities | None = None,
    metadata: dict[str, Any] | None = None,
) -> EnrichedModelInfo:
    """Merge static vendor metadata, caller hints, and dynamic cache."""
    model_key = f"{provider}:{name}"
    static = get_static_model_metadata(provider, name)
    static_caps = ModelCapabilities(
        vision=static.get("vision"),
        tools=static.get("tools"),
        audio_input=static.get("audio_input"),
        audio_output=static.get("audio_output"),
        structured_output=static.get("structured_output"),
        is_local=static.get("is_local"),
    )
    merged = static_caps.merge_dynamic(capabilities or ModelCapabilities())
    dynamic_caps, dynamic_sources, dynamic_updated = _load_dynamic_caps(model_key)
    merged = merged.merge_dynamic(dynamic_caps)

    sources: dict[str, CapabilitySource] = {}
    updated_at: dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat()
    for key in ("vision", "tools", "audio_input", "audio_output", "structured_output", "is_local"):
        if key in dynamic_sources:
            sources[key] = "dynamic"
            updated_at[key] = dynamic_updated.get(key, now)
        elif getattr(static_caps, key) is not None:
            sources[key] = "static"
            updated_at[key] = static.get("_updated_at", now)
        elif capabilities is not None and getattr(capabilities, key) is not None:
            sources[key] = "merged"
            updated_at[key] = now

    ctx = context_window if context_window is not None else static.get("context_window")
    max_out = max_output_tokens if max_output_tokens is not None else static.get("max_output_tokens")
    pricing = {
        "input_per_million": static.get("input_price_per_million"),
        "output_per_million": static.get("output_price_per_million"),
    }

    return EnrichedModelInfo(
        name=name,
        provider=provider,
        context_window=ctx,
        max_output_tokens=max_out,
        capabilities=merged,
        capability_sources=sources,
        capability_updated_at=updated_at,
        pricing=pricing,
        metadata=dict(metadata or {}),
    )


def learn_capabilities(model_key: str, caps: ModelCapabilities, source: str = "dynamic") -> None:
    cache = get_capability_cache()
    now = datetime.now(timezone.utc).isoformat()
    entry = cache.all().get(model_key, {})
    existing_caps = entry.get("capabilities", {})
    existing_sources = entry.get("sources", {})
    existing_updated = entry.get("updated_at", {})
    for key, val in caps.to_dict().items():
        if val == "unknown":
            continue
        existing_caps[key] = val == "true"
        existing_sources[key] = source
        existing_updated[key] = now
    cache.learn_entry(model_key, existing_caps, existing_sources, existing_updated)


def provider_config_fingerprint(provider: str, *, connection_id: str | None = None) -> str:
    from app.core.config import settings

    parts: list[str] = [provider]
    if connection_id:
        parts.append(f"conn:{connection_id}")
        try:
            from app.providers.connections.service import connection_service

            conn = connection_service.get_connection(connection_id)
            parts.extend([
                str(conn.get("base_url") or ""),
                "key:" + ("1" if conn.get("credential_configured") else "0"),
                str(conn.get("revision", 0)),
            ])
        except Exception:  # noqa: BLE001
            pass
    elif provider == "openai":
        parts.extend([settings.openai_base_url or "", "key:" + ("1" if settings.openai_api_key else "0")])
    elif provider == "anthropic":
        parts.extend([settings.anthropic_base_url or "", "key:" + ("1" if settings.anthropic_api_key else "0")])
    elif provider == "ollama":
        parts.append(settings.ollama_base_url or "")
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return digest
