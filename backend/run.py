#!/usr/bin/env python
"""BoetClaw backend entry script."""

from __future__ import annotations

import importlib.util
import sys


def _preflight() -> None:
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        print(
            "BoetClaw backend 需要 Python 3.11-3.13。\n"
            f"当前 Python: {sys.version.split()[0]}\n\n"
            "请安装 Python 3.12 或 3.13 后重新创建虚拟环境，例如：\n"
            "  py -3.12 -m venv .venv\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
            "  .\\.venv\\Scripts\\python.exe run.py",
            file=sys.stderr,
        )
        raise SystemExit(1)

    missing = [
        name
        for name in ("uvicorn", "fastapi", "structlog", "deepagents", "langchain", "pydantic_settings")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        print(
            "缺少后端依赖: " + ", ".join(missing) + "\n\n"
            "看起来你正在使用全局 Python，而不是项目虚拟环境。\n"
            "请在 backend 目录执行：\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
            "  .\\.venv\\Scripts\\python.exe run.py\n\n"
            "如果还没有 .venv，请先运行项目根目录的：\n"
            "  .\\scripts\\install.ps1",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    _preflight()

    import uvicorn

    from app.core.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
