"""File path guardian: blocks access to sensitive directories/files."""

from __future__ import annotations

from app.core.config import settings
from app.security.execution_level import GuardSeverity
from app.security.guardians.base import BaseGuardian
from app.security.models import GuardFinding, GuardResult

# Args that commonly carry file paths
PATH_ARG_KEYS = ("file_path", "path", "filename", "file", "target", "dir", "directory")


class FilePathToolGuardian(BaseGuardian):
    name = "file_guardian"

    def __init__(self, deny_dirs: list[str] | None = None) -> None:
        self._deny = [d.lower() for d in (deny_dirs if deny_dirs is not None else settings.file_deny_dirs_list)]

    def _extract_paths(self, args: dict) -> list[str]:
        paths: list[str] = []
        for k, v in args.items():
            if isinstance(v, str) and (k.lower() in PATH_ARG_KEYS or "/" in v or "\\" in v or v.startswith(".")):
                paths.append(v)
        return paths

    def inspect(self, tool_name: str, args: dict) -> GuardResult:
        for p in self._extract_paths(args):
            pl = p.lower().replace("\\", "/")
            for deny in self._deny:
                if deny and (f"/{deny}" in f"/{pl}" or pl.endswith(deny) or f"{deny}/" in pl or pl == deny):
                    return GuardResult(
                        allowed=False,
                        reason=f"禁止访问敏感路径: {p}",
                        findings=[GuardFinding(GuardSeverity.CRITICAL, "file_access", f"blocked path {p}", self.name)],
                    )
        return GuardResult()
