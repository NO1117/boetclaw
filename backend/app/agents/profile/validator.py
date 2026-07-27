"""AgentProfile validation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.agents.profile.metrics import validate_timer
from app.agents.profile.models import (
    EDITABLE_FIELDS,
    MAX_DESCRIPTION_CHARS,
    MAX_DISPLAY_NAME_CHARS,
    MAX_SYSTEM_PROMPT_CHARS,
    AgentProfile,
    EffectiveAgentConfig,
    ProfileValidationResult,
)
from app.agents.profile.security import scan_profile_secrets
from app.core.config import settings
from app.providers.manager import provider_manager
from app.tools.builtin import get_builtin_tools
from app.tools.mcp_manager import mcp_manager


class ProfileValidationError(ValueError):
    def __init__(self, message: str, errors: list[str] | None = None, status_code: int = 400) -> None:
        super().__init__(message)
        self.errors = errors or [message]
        self.status_code = status_code


def _known_tool_names() -> set[str]:
    names = {tool.name for tool in get_builtin_tools()}
    names.update(tool.name for tool in mcp_manager.tools)
    try:
        from app.plugins.registry import plugin_registry

        names.update(tool.name for tool in plugin_registry.enabled_tools())
    except Exception:  # noqa: BLE001
        pass
    return names


def _safe_tool_names() -> set[str]:
    blocked = {"write_file", "edit_file", "delete"}
    return _known_tool_names() - blocked


def resolve_effective(profile: AgentProfile) -> EffectiveAgentConfig:
    provider = profile.provider.strip() or settings.llm_provider
    model = profile.model.strip() or settings.llm_model
    memory_mode = profile.memory_mode
    if memory_mode == "inherit":
        memory_mode = settings.memory_auto_mode if settings.memory_auto_mode in {"off", "review", "auto"} else "review"
    return EffectiveAgentConfig(
        provider=provider,
        model=model,
        model_string=f"{provider}:{model}",
        temperature=profile.temperature,
        max_output_tokens=profile.max_output_tokens,
        tool_policy=profile.tool_policy,
        tool_allowlist=list(profile.tool_allowlist),
        memory_mode=memory_mode,
        default_language=profile.default_language or settings.lang,
        enabled=profile.enabled,
        system_prompt=profile.system_prompt,
        revision=profile.revision,
    )


def merge_profile(current: AgentProfile, updates: dict[str, Any]) -> AgentProfile:
    unknown = [key for key in updates if key not in EDITABLE_FIELDS]
    if unknown:
        raise ProfileValidationError(f"未知字段: {', '.join(sorted(unknown))}")
    data = current.model_dump()
    data.update({key: updates[key] for key in EDITABLE_FIELDS if key in updates})
    data["agent_id"] = current.agent_id
    data["revision"] = current.revision
    data["schema_version"] = current.schema_version
    data["created_at"] = current.created_at
    try:
        return AgentProfile.model_validate(data)
    except ValidationError as exc:
        raise ProfileValidationError("配置字段无效", [str(exc)]) from exc


def validate_profile(profile: AgentProfile, *, is_default_agent: bool = False) -> ProfileValidationResult:
    with validate_timer():
        errors: list[str] = []
        warnings: list[str] = []

        if len(profile.display_name) > MAX_DISPLAY_NAME_CHARS:
            errors.append(f"显示名称超过 {MAX_DISPLAY_NAME_CHARS} 字符")
        if len(profile.description) > MAX_DESCRIPTION_CHARS:
            errors.append(f"描述超过 {MAX_DESCRIPTION_CHARS} 字符")
        if len(profile.system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
            errors.append(f"提示词超过 {MAX_SYSTEM_PROMPT_CHARS} 字符")

        secret_errors = scan_profile_secrets(profile.model_dump())
        errors.extend(secret_errors)

        if profile.temperature is not None and not (0.0 <= profile.temperature <= 2.0):
            errors.append("temperature 必须在 0.0 到 2.0 之间")
        if profile.max_output_tokens is not None and profile.max_output_tokens <= 0:
            errors.append("max_output_tokens 必须为正整数")

        effective = resolve_effective(profile)
        if profile.provider.strip() or profile.model.strip():
            try:
                provider_manager.get(effective.provider)
            except ValueError:
                errors.append(f"未知 Provider: {effective.provider}")
            else:
                known = {m.name for m in provider_manager.list_models(effective.provider)}
                if effective.model not in known:
                    errors.append(f"未知模型: {effective.provider}/{effective.model}")

        known_tools = _known_tool_names()
        if profile.tool_policy == "allowlist":
            if not profile.tool_allowlist:
                errors.append("allowlist 策略需要至少一个工具")
            unknown_tools = sorted(set(profile.tool_allowlist) - known_tools)
            if unknown_tools:
                errors.append(f"未知工具: {', '.join(unknown_tools)}")
        elif profile.tool_policy == "safe_only":
            if profile.tool_allowlist:
                warnings.append("safe_only 策略忽略 tool_allowlist")

        if is_default_agent and not profile.enabled:
            errors.append("默认 Agent 不可禁用")

        return ProfileValidationResult(valid=not errors, errors=errors, warnings=warnings)


def filter_tools_for_policy(tool_policy: str, allowlist: list[str]) -> set[str] | None:
    if tool_policy == "inherit":
        return None
    if tool_policy == "safe_only":
        return _safe_tool_names()
    if tool_policy == "allowlist":
        return set(allowlist)
    return None
