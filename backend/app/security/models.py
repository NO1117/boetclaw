"""Guard data models."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.security.execution_level import GuardSeverity


@dataclass
class GuardFinding:
    severity: GuardSeverity
    category: str
    message: str
    guardian: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.label,
            "category": self.category,
            "message": self.message,
            "guardian": self.guardian,
        }


@dataclass
class GuardResult:
    allowed: bool = True
    requires_approval: bool = False
    findings: list[GuardFinding] = field(default_factory=list)
    reason: str = ""

    @property
    def max_severity(self) -> GuardSeverity:
        if not self.findings:
            return GuardSeverity.INFO
        return max((f.severity for f in self.findings), key=lambda s: s.value)

    def merge(self, other: "GuardResult") -> "GuardResult":
        return GuardResult(
            allowed=self.allowed and other.allowed,
            requires_approval=self.requires_approval or other.requires_approval,
            findings=self.findings + other.findings,
            reason=self.reason or other.reason,
        )

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "max_severity": self.max_severity.label,
            "findings": [f.to_dict() for f in self.findings],
        }
