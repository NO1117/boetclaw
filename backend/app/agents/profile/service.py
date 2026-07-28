"""Agent profile orchestration: apply, rollback, clone, import/export."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.agents.profile.metrics import profile_metrics
from app.agents.profile.models import (
    CURRENT_SCHEMA_VERSION,
    AgentProfile,
    ProfileResponse,
    ProfileValidationResult,
)
from app.agents.profile.security import ProfileSecurityError, scan_profile_secrets, validate_agent_id
from app.agents.profile.snapshot import capture_snapshot
from app.agents.profile.store import ProfileConflictError, ProfileStore, ProfileStoreError
from app.agents.profile.validator import (
    ProfileValidationError,
    merge_profile,
    resolve_effective,
    validate_profile,
)
from app.agents.profile.versions import VersionRepository
from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger

logger = get_logger("agent_profile_service")

EXPORT_VERSION = 1


class AgentProfileService:
    def __init__(
        self,
        store: ProfileStore | None = None,
        versions: VersionRepository | None = None,
    ) -> None:
        self.store = store or ProfileStore()
        self.versions = versions or VersionRepository()

    def _audit(self, audit_event: str, agent_id: str, *, revision: int | None = None, fields: list[str] | None = None) -> None:
        payload: dict[str, Any] = {"agent_id": agent_id, "audit_event": audit_event}
        if revision is not None:
            payload["revision"] = revision
        if fields:
            payload["changed_fields"] = fields
        logger.info("agent_profile_audit", **payload)
        emit_event(EventType.RUN_STATUS, payload)

    def get_or_create(self, agent_id: str) -> AgentProfile:
        validate_agent_id(agent_id)
        try:
            return self.store.load(agent_id)
        except ProfileStoreError as exc:
            if exc.status_code != 404:
                raise
            return self.store.load(agent_id, create_default=True)

    def build_response(self, profile: AgentProfile) -> ProfileResponse:
        effective = resolve_effective(profile)
        apply_state = self.store.read_apply_state(profile.agent_id)
        return ProfileResponse(
            agent_id=profile.agent_id,
            configured=profile.editable_dict(),
            effective={
                **effective.model_dump(),
                "display_name": profile.display_name,
                "description": profile.description,
                "avatar_color": profile.avatar_color,
            },
            revision=profile.revision,
            apply_state=apply_state,
        )

    def validate_payload(
        self,
        agent_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int | None = None,
    ) -> ProfileValidationResult:
        current = self.get_or_create(agent_id)
        if expected_revision is not None and current.revision != expected_revision:
            profile_metrics.record_conflict()
            return ProfileValidationResult(
                valid=False,
                errors=[f"revision 冲突：期望 {expected_revision}，当前 {current.revision}"],
            )
        merged = merge_profile(current, payload)
        return validate_profile(merged, is_default_agent=agent_id == settings.default_agent_id)

    async def apply_profile(
        self,
        agent_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int,
        operator: str = "system",
    ) -> ProfileResponse:
        current = self.get_or_create(agent_id)
        merged = merge_profile(current, payload)
        result = validate_profile(merged, is_default_agent=agent_id == settings.default_agent_id)
        if not result.valid:
            profile_metrics.record_save(success=False)
            raise ProfileValidationError("配置验证失败", result.errors)

        previous = current.model_dump()
        merged.revision = current.revision + 1
        merged.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            saved = self.store.save(merged, expected_revision=expected_revision)
        except ProfileConflictError as exc:
            profile_metrics.record_conflict()
            self._audit("profile_conflict", agent_id, revision=exc.actual_revision)
            raise

        version = self.versions.make_record(
            profile_dict=saved.model_dump(),
            previous=previous,
            operator=operator,
        )
        self.versions.append(version)
        self._audit("profile_updated", agent_id, revision=saved.revision, fields=version.changed_fields)

        apply_ok = await self._apply_runtime(agent_id, saved)
        if not apply_ok:
            restored = self.store.restore_backup(agent_id)
            if restored is not None:
                profile_metrics.record_rollback()
                self._audit("profile_rollback", agent_id, revision=restored.revision)
                saved = restored
            profile_metrics.record_save(success=False)
        else:
            profile_metrics.record_save(success=True)

        return self.build_response(saved)

    async def _apply_runtime(self, agent_id: str, profile: AgentProfile) -> bool:
        started = time.perf_counter()
        state = {
            "revision": profile.revision,
            "status": "pending",
            "applied_at": "",
            "error_summary": "",
        }
        try:
            from app.agents.graph_cache import get_graph_cache
            from app.agents.multi_agent_manager import multi_agent_manager

            get_graph_cache().invalidate_agent(agent_id)
            ws = multi_agent_manager.get_workspace(agent_id)
            if ws is not None:
                ws.config = profile.editable_dict()
                await multi_agent_manager.reload_agent(agent_id)
            elapsed_ms = (time.perf_counter() - started) * 1000
            profile_metrics.record_rebuild(elapsed_ms)
            state.update(
                {
                    "status": "applied",
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                    "error_summary": "",
                }
            )
            self.store.write_apply_state(agent_id, state)
            self._audit("profile_applied", agent_id, revision=profile.revision)
            return True
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - started) * 1000
            profile_metrics.record_rebuild(elapsed_ms)
            state.update(
                {
                    "status": "failed",
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                    "error_summary": str(exc)[:200],
                }
            )
            self.store.write_apply_state(agent_id, state)
            logger.error("agent_profile_apply_failed", agent_id=agent_id, error=str(exc))
            return False

    async def rollback(self, agent_id: str, target_revision: int, *, operator: str = "system") -> ProfileResponse:
        record = self.versions.get(agent_id, target_revision)
        if record is None:
            raise ProfileStoreError(f"版本 {target_revision} 不存在", 404)
        current = self.get_or_create(agent_id)
        snapshot = dict(record.snapshot)
        snapshot["revision"] = current.revision + 1
        snapshot["schema_version"] = CURRENT_SCHEMA_VERSION
        snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
        profile = AgentProfile.model_validate(snapshot)
        result = validate_profile(profile, is_default_agent=agent_id == settings.default_agent_id)
        if not result.valid:
            raise ProfileValidationError("回滚目标无效", result.errors)

        previous = current.model_dump()
        saved = self.store.save(profile, expected_revision=current.revision)
        version = self.versions.make_record(
            profile_dict=saved.model_dump(),
            previous=previous,
            operator=operator,
        )
        version.changed_fields = ["rollback", f"from_revision:{target_revision}"]
        self.versions.append(version)
        await self._apply_runtime(agent_id, saved)
        self._audit("profile_rollback_applied", agent_id, revision=saved.revision)
        return self.build_response(saved)

    def list_versions(self, agent_id: str, *, offset: int = 0, limit: int = 20) -> dict[str, Any]:
        rows, total = self.versions.list_revisions(agent_id, offset=offset, limit=limit)
        return {"agent_id": agent_id, "total": total, "offset": offset, "limit": limit, "versions": rows}

    def get_version_detail(self, agent_id: str, revision: int) -> dict[str, Any]:
        record = self.versions.get(agent_id, revision)
        if record is None:
            raise ProfileStoreError(f"版本 {revision} 不存在", 404)
        current = self.get_or_create(agent_id)
        diff = VersionRepository.diff_fields(current.editable_dict(), record.snapshot)
        return {
            "agent_id": agent_id,
            "revision": revision,
            "record": {
                "revision": record.revision,
                "created_at": record.created_at,
                "changed_fields": record.changed_fields,
                "operator": record.operator,
            },
            "snapshot": {key: record.snapshot.get(key) for key in sorted(record.snapshot.keys()) if key in record.snapshot},
            "diff_from_current": diff,
        }

    async def clone_agent(
        self,
        source_id: str,
        *,
        new_agent_id: str | None = None,
        copy_skills: bool = False,
        operator: str = "system",
    ) -> ProfileResponse:
        source = self.get_or_create(source_id)
        target_id = validate_agent_id(new_agent_id or f"{source_id}-copy-{uuid.uuid4().hex[:6]}")
        if self.store.exists(target_id):
            raise ProfileStoreError(f"Agent 已存在: {target_id}")

        from app.agents.multi_agent_manager import multi_agent_manager

        multi_agent_manager.create(target_id)
        cloned = source.model_copy(
            update={
                "agent_id": target_id,
                "display_name": f"{source.display_name or source_id} (副本)",
                "revision": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        saved = self.store.save(cloned, expected_revision=None)
        if copy_skills:
            import shutil

            src_skills = multi_agent_manager._root / source_id / "skills"
            dst_skills = multi_agent_manager._root / target_id / "skills"
            if src_skills.is_dir():
                dst_skills.mkdir(parents=True, exist_ok=True)
                for child in src_skills.iterdir():
                    if child.is_dir():
                        target = dst_skills / child.name
                        if target.exists():
                            continue
                        shutil.copytree(child, target)

        version = self.versions.make_record(profile_dict=saved.model_dump(), previous=None, operator=operator)
        self.versions.append(version)
        await self._apply_runtime(target_id, saved)
        self._audit("profile_cloned", target_id, revision=saved.revision, fields=["clone", source_id])
        return self.build_response(saved)

    def export_profile(self, agent_id: str) -> dict[str, Any]:
        profile = self.get_or_create(agent_id)
        exportable = profile.editable_dict()
        exportable["agent_id"] = profile.agent_id
        errors = scan_profile_secrets(exportable)
        if errors:
            raise ProfileValidationError("导出内容含敏感字段", errors)
        self._audit("profile_exported", agent_id, revision=profile.revision)
        return {
            "export_version": EXPORT_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "profile": exportable,
        }

    async def import_profile(
        self,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        operator: str = "system",
    ) -> ProfileResponse:
        if int(payload.get("export_version", 0) or 0) != EXPORT_VERSION:
            raise ProfileValidationError("不支持的导出版本")
        profile_data_raw = payload.get("profile")
        if not isinstance(profile_data_raw, dict):
            raise ProfileValidationError("导入缺少 profile 对象")
        profile_data = dict(profile_data_raw)
        target_id = validate_agent_id(agent_id or str(profile_data_raw.get("agent_id", "")))
        profile_data.pop("agent_id", None)
        secret_errors = scan_profile_secrets(profile_data)
        if secret_errors:
            raise ProfileValidationError("导入内容含敏感字段", secret_errors)

        from app.agents.multi_agent_manager import multi_agent_manager

        if not multi_agent_manager.is_registered(target_id):
            multi_agent_manager.create(target_id)

        existed_before = self.store.exists(target_id)
        current = self.get_or_create(target_id)
        merged = merge_profile(current, profile_data)
        merged.agent_id = target_id
        result = validate_profile(merged, is_default_agent=target_id == settings.default_agent_id)
        if not result.valid:
            raise ProfileValidationError("导入验证失败", result.errors)

        merged.revision = current.revision + 1 if existed_before else 1
        saved = self.store.save(merged, expected_revision=current.revision if existed_before else None)
        version = self.versions.make_record(profile_dict=saved.model_dump(), previous=current.model_dump(), operator=operator)
        self.versions.append(version)
        await self._apply_runtime(target_id, saved)
        self._audit("profile_imported", target_id, revision=saved.revision)
        return self.build_response(saved)

    def effective_for_agent(self, agent_id: str) -> dict[str, Any]:
        profile = self.get_or_create(agent_id)
        effective = resolve_effective(profile)
        return capture_snapshot(effective)


profile_service = AgentProfileService()
