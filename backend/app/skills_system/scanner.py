"""Skill security scanner: pre-install checks for secrets and dangerous code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanFinding:
    file: str
    line: int
    category: str
    snippet: str

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "category": self.category, "snippet": self.snippet}


# (regex, category)
SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), "openai_key"),
    (re.compile(r"AKIA[0-9A-Z]{12,}"), "aws_key"),
    (re.compile(r"(?i)password\s*=\s*['\"][^'\"]+['\"]"), "hardcoded_password"),
    (re.compile(r"(?i)secret\s*=\s*['\"][^'\"]{6,}['\"]"), "hardcoded_secret"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github_token"),
]

DANGER_PATTERNS = [
    (re.compile(r"\bos\.system\s*\("), "os_system"),
    (re.compile(r"\bsubprocess\.(Popen|call|run)\s*\("), "subprocess"),
    (re.compile(r"\beval\s*\("), "eval"),
    (re.compile(r"\bexec\s*\("), "exec"),
    (re.compile(r"__import__\s*\("), "dynamic_import"),
    (re.compile(r"(?i)rm\s+-rf"), "rm_rf"),
]

SCAN_EXTS = {".py", ".sh", ".js", ".ts", ".md", ".txt", ".json", ".yaml", ".yml"}


class SkillScanner:
    def scan(self, skill_dir: str | Path) -> list[ScanFinding]:
        base = Path(skill_dir)
        findings: list[ScanFinding] = []
        if not base.exists():
            return findings
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in SCAN_EXTS:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            rel = str(f.relative_to(base))
            for i, line in enumerate(lines, 1):
                for pat, cat in SECRET_PATTERNS + DANGER_PATTERNS:
                    if pat.search(line):
                        findings.append(ScanFinding(file=rel, line=i, category=cat, snippet=line.strip()[:120]))
        return findings

    def is_safe(self, skill_dir: str | Path) -> bool:
        return len(self.scan(skill_dir)) == 0


skill_scanner = SkillScanner()
