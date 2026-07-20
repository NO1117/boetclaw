"""Approval service: tracks pending tool-approval requests."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.execution_ref import ExecutionRef


@dataclass
class ApprovalRequest:
    id: str
    tool: str
    args: dict[str, Any]
    findings: list[dict]
    thread_id: str = ""
    execution_ref: ExecutionRef | None = None
    idempotency_key: str = ""
    status: str = "pending"  # pending|resuming|approved|rejected|resume_failed|expired
    decision: str = ""
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool,
            "args": self.args,
            "findings": self.findings,
            "thread_id": self.thread_id,
            "execution_ref": self.execution_ref.model_dump() if self.execution_ref else None,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "decision": self.decision,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        raw_ref = data.get("execution_ref")
        execution_ref = None
        if isinstance(raw_ref, dict):
            try:
                execution_ref = ExecutionRef.model_validate(raw_ref)
            except ValueError:
                execution_ref = None
        return cls(
            id=str(data.get("id", "")),
            tool=str(data.get("tool", "")),
            args=data.get("args") if isinstance(data.get("args"), dict) else {},
            findings=data.get("findings") if isinstance(data.get("findings"), list) else [],
            thread_id=str(data.get("thread_id", "")),
            execution_ref=execution_ref,
            idempotency_key=str(data.get("idempotency_key", "")),
            status=str(data.get("status", "pending")),
            decision=str(data.get("decision", "")),
            error=str(data.get("error", "")),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            updated_at=str(
                data.get("updated_at")
                or data.get("created_at")
                or datetime.now(timezone.utc).isoformat()
            ),
        )


class ApprovalStateError(ValueError):
    pass


class ApprovalService:
    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path or (settings.workspace_dir / "security" / "approval_history.json")
        self._requests: dict[str, ApprovalRequest] = {}
        self._by_key: dict[str, str] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.persist_path.exists():
            return
        try:
            rows = json.loads(self.persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            req = ApprovalRequest.from_dict(row)
            if req.id:
                if req.status == "resuming":
                    req.status = "resume_failed"
                    req.error = (
                        "服务在恢复处理中重启，工具是否已产生副作用无法判定；"
                        "为防止重复执行，该审批不可自动重试"
                    )
                    req.updated_at = datetime.now(timezone.utc).isoformat()
                self._requests[req.id] = req
                if req.idempotency_key:
                    self._by_key[req.idempotency_key] = req.id
        if any(r.status == "resume_failed" and "恢复处理中重启" in r.error for r in self._requests.values()):
            self._save()

    def _save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [r.to_dict() for r in self.list_all()]
        temp_path = self.persist_path.with_suffix(f"{self.persist_path.suffix}.tmp")
        temp_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.persist_path)

    @staticmethod
    def make_idempotency_key(agent_id: str, thread_id: str, tool_call_id: str) -> str:
        if not agent_id or not thread_id or not tool_call_id:
            raise ApprovalStateError("工具审批缺少 agent/thread/tool_call 稳定标识")
        return f"{agent_id}\x1f{thread_id}\x1f{tool_call_id}"

    def create(
        self,
        tool: str,
        args: dict,
        findings: list[dict],
        thread_id: str = "",
        execution_ref: ExecutionRef | None = None,
        idempotency_key: str = "",
    ) -> ApprovalRequest:
        with self._lock:
            req = ApprovalRequest(
                id=uuid.uuid4().hex[:12],
                tool=tool,
                args=args,
                findings=findings,
                thread_id=execution_ref.thread_id if execution_ref else thread_id,
                execution_ref=execution_ref,
                idempotency_key=idempotency_key,
            )
            self._requests[req.id] = req
            if idempotency_key:
                self._by_key[idempotency_key] = req.id
            self._save()
            return req

    def get_or_create(
        self,
        *,
        tool: str,
        args: dict,
        findings: list[dict],
        agent_id: str,
        thread_id: str,
        tool_call_id: str,
    ) -> ApprovalRequest:
        key = self.make_idempotency_key(agent_id, thread_id, tool_call_id)
        with self._lock:
            existing_id = self._by_key.get(key)
            existing = self._requests.get(existing_id) if existing_id else None
            if existing is not None:
                if existing.tool != tool or existing.args != args:
                    raise ApprovalStateError("同一工具调用标识对应的审批内容不一致")
                if existing.status not in {"pending", "resuming"}:
                    raise ApprovalStateError(f"该工具调用审批已终结：{existing.status}")
                return existing
            return self.create(
                tool,
                args,
                findings,
                thread_id=thread_id,
                idempotency_key=key,
            )

    def bind_execution_ref(self, req_id: str, execution_ref: ExecutionRef) -> ApprovalRequest | None:
        with self._lock:
            req = self._requests.get(req_id)
            if not req or req.status != "pending":
                return None
            if req.execution_ref is not None and req.execution_ref != execution_ref:
                return None
            req.execution_ref = execution_ref
            req.thread_id = execution_ref.thread_id
            req.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return req

    def get(self, req_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._requests.get(req_id)

    def list_pending(self) -> list[ApprovalRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.status == "pending"]

    def list_attention(self) -> list[ApprovalRequest]:
        with self._lock:
            return [
                r
                for r in self.list_all()
                if r.status in {"pending", "resuming", "resume_failed", "expired"}
            ]

    def list_all(self) -> list[ApprovalRequest]:
        with self._lock:
            return sorted(self._requests.values(), key=lambda r: r.created_at, reverse=True)

    def begin_resume(self, req_id: str, decision: str) -> ApprovalRequest:
        if decision not in {"approve", "reject"}:
            raise ApprovalStateError("无效审批决定")
        with self._lock:
            req = self._requests.get(req_id)
            if req is None:
                raise ApprovalStateError("审批记录不存在")
            if req.status != "pending":
                raise ApprovalStateError(f"审批已不可恢复：{req.status}")
            req.status = "resuming"
            req.decision = decision
            req.error = ""
            req.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return req

    def resolve(self, req_id: str, decision: str) -> ApprovalRequest | None:
        with self._lock:
            req = self._requests.get(req_id)
            if not req or req.status != "resuming" or req.decision != decision:
                return None
            req.status = "approved" if decision == "approve" else "rejected"
            req.error = ""
            req.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return req

    def mark_resume_failed(self, req_id: str, error: str) -> ApprovalRequest | None:
        with self._lock:
            req = self._requests.get(req_id)
            if not req or req.status != "resuming":
                return None
            req.status = "resume_failed"
            req.error = (
                f"{error}；恢复结果可能包含未写回的工具副作用，"
                "为防止重复执行，该审批不可自动重试"
            )
            req.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return req

    def expire_pending_for_restart(self, checkpoint_backend: str) -> int:
        """Expire restart-lost approvals only for the explicit memory backend."""
        if checkpoint_backend != "memory":
            return 0
        with self._lock:
            changed = 0
            for req in self._requests.values():
                if req.status != "pending":
                    continue
                req.status = "expired"
                req.error = "memory checkpoint 不支持跨进程重启恢复"
                req.updated_at = datetime.now(timezone.utc).isoformat()
                changed += 1
            if changed:
                self._save()
            return changed


approval_service = ApprovalService()
