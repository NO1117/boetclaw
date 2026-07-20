"""Export FastAPI OpenAPI schema to a canonical JSON file.

Usage (from backend/):
  PYTHONPATH=. python scripts/export_openapi.py
  PYTHONPATH=. python scripts/export_openapi.py --out openapi.snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _canonical(obj: object) -> object:
    """Recursively sort dict keys for stable diffs."""
    if isinstance(obj, dict):
        return {k: _canonical(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_canonical(item) for item in obj]
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description="Export BoetClaw OpenAPI schema")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "openapi.snapshot.json",
        help="Output path (default: backend/openapi.snapshot.json)",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.main import app  # noqa: E402

    schema = _canonical(app.openapi())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths = len(schema.get("paths", {})) if isinstance(schema, dict) else 0
    print(f"Wrote {args.out} ({paths} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
