"""Input attachment requirements vs model capability compatibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.providers.capabilities import EnrichedModelInfo, enrich_model
from app.providers.manager import provider_manager

CompatibilityStatus = Literal["compatible", "incompatible", "unknown_risk"]


@dataclass(frozen=True)
class InputRequirements:
    requires_vision: bool = False
    image_count: int = 0
    document_count: int = 0
    attachment_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "requires_vision": self.requires_vision,
            "image_count": self.image_count,
            "document_count": self.document_count,
            "attachment_count": self.attachment_count,
        }


@dataclass
class CompatibilityResult:
    status: CompatibilityStatus
    model: str
    provider: str
    missing_capabilities: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "model": self.model,
            "provider": self.provider,
            "missing_capabilities": list(self.missing_capabilities),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }


def derive_input_requirements(
    *,
    has_images: bool = False,
    image_count: int = 0,
    attachment_count: int = 0,
    document_count: int = 0,
) -> InputRequirements:
    count = image_count or (1 if has_images else 0)
    return InputRequirements(
        requires_vision=count > 0,
        image_count=count,
        document_count=document_count,
        attachment_count=attachment_count or count + document_count,
    )


def check_model_compatibility(
    provider: str,
    model: str,
    requirements: InputRequirements,
) -> CompatibilityResult:
    raw_models = {m.name: m for m in provider_manager.get(provider).list_models()}
    base = raw_models.get(model)
    if base is None:
        return CompatibilityResult(
            status="incompatible",
            model=model,
            provider=provider,
            reason=f"未知模型: {provider}/{model}",
        )

    enriched = enrich_model(
        name=base.name,
        provider=base.provider,
        context_window=base.context_window or None,
        max_output_tokens=getattr(base, "max_output_tokens", None),
        capabilities=None,
        metadata=dict(base.metadata),
    )
    return check_enriched_compatibility(enriched, requirements)


def check_enriched_compatibility(
    model_info: EnrichedModelInfo,
    requirements: InputRequirements,
) -> CompatibilityResult:
    missing: list[str] = []
    warnings: list[str] = []

    if requirements.requires_vision:
        vision = model_info.capabilities.vision
        if vision is False:
            missing.append("vision")
        elif vision is None:
            warnings.append("模型视觉能力未知，发送前请确认兼容性")

    if missing:
        cap_label = "、".join(_capability_label(c) for c in missing)
        return CompatibilityResult(
            status="incompatible",
            model=model_info.name,
            provider=model_info.provider,
            missing_capabilities=missing,
            reason=f"当前输入需要 {cap_label}，该模型不支持",
        )

    if warnings:
        return CompatibilityResult(
            status="unknown_risk",
            model=model_info.name,
            provider=model_info.provider,
            warnings=warnings,
            reason=warnings[0],
        )

    return CompatibilityResult(
        status="compatible",
        model=model_info.name,
        provider=model_info.provider,
        reason="与当前输入兼容",
    )


def _capability_label(cap: str) -> str:
    return {
        "vision": "视觉理解",
        "tools": "工具调用",
        "audio_input": "音频输入",
        "audio_output": "音频输出",
        "structured_output": "结构化输出",
    }.get(cap, cap)


class ModelCompatibilityError(Exception):
    error_code = "MODEL_INCOMPATIBLE"

    def __init__(
        self,
        message: str,
        *,
        missing_capabilities: list[str] | None = None,
        provider: str = "",
        model: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = 400
        self.missing_capabilities = missing_capabilities or []
        self.provider = provider
        self.model = model

    def to_detail(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "provider": self.provider,
            "model": self.model,
            "missing_capabilities": self.missing_capabilities,
        }
