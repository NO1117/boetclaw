"""Compare live OpenAPI against the committed snapshot for breaking changes.

Intentional scope (minimal, maintainable — not a full OAS diff product):

Breaking (fail CI):
  - Removed path or HTTP method
  - New required query/path/header parameter
  - New required requestBody property (application/json object)
  - Removed success (2xx) response status code

Non-breaking / ignored (avoid brittle failures):
  - descriptions, summaries, examples, titles, tags order
  - added optional parameters / properties / paths
  - response schema field renames inside 2xx (too noisy without codegen clients)
  - operationId / servers / components not referenced by the rules above

Usage (from backend/):
  PYTHONPATH=. python scripts/check_openapi_breaking.py
  PYTHONPATH=. python scripts/check_openapi_breaking.py --update
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_props(schema: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    """Return (all_props, required_props) for a JSON Schema object."""
    if not schema or not isinstance(schema, dict):
        return set(), set()
    if schema.get("type") == "object" or "properties" in schema:
        props = set((schema.get("properties") or {}).keys())
        required = set(schema.get("required") or [])
        return props, required
    # unwrap common wrappers
    for key in ("allOf", "oneOf", "anyOf"):
        items = schema.get(key)
        if isinstance(items, list):
            all_props: set[str] = set()
            all_req: set[str] = set()
            for item in items:
                if isinstance(item, dict):
                    p, r = _schema_props(item)
                    all_props |= p
                    all_req |= r
            if all_props or all_req:
                return all_props, all_req
    return set(), set()


def _resolve_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return schema
        node = node[part]
    return node if isinstance(node, dict) else schema


def _json_body_schema(op: dict[str, Any], root: dict[str, Any]) -> dict[str, Any] | None:
    body = op.get("requestBody")
    if not isinstance(body, dict):
        return None
    content = body.get("content") or {}
    media = content.get("application/json") or next(iter(content.values()), None)
    if not isinstance(media, dict):
        return None
    schema = media.get("schema")
    if not isinstance(schema, dict):
        return None
    return _resolve_ref(schema, root)


def _required_params(op: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for param in op.get("parameters") or []:
        if not isinstance(param, dict):
            continue
        if param.get("required") is True:
            loc = param.get("in", "?")
            name = param.get("name", "?")
            out.add(f"{loc}:{name}")
    return out


def _success_statuses(op: dict[str, Any]) -> set[str]:
    responses = op.get("responses") or {}
    return {code for code in responses if str(code).startswith("2")}


def _collect_ops(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    paths = spec.get("paths") or {}
    ops: dict[str, dict[str, Any]] = {}
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
            }:
                continue
            if isinstance(op, dict):
                ops[f"{method.upper()} {path}"] = op
    return ops


def find_breaking(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    breaks: list[str] = []
    base_ops = _collect_ops(baseline)
    cur_ops = _collect_ops(current)

    for key, base_op in base_ops.items():
        if key not in cur_ops:
            breaks.append(f"removed operation: {key}")
            continue
        cur_op = cur_ops[key]

        base_req = _required_params(base_op)
        cur_req = _required_params(cur_op)
        for param in sorted(cur_req - base_req):
            breaks.append(f"new required parameter on {key}: {param}")

        base_schema = _json_body_schema(base_op, baseline)
        cur_schema = _json_body_schema(cur_op, current)
        _, base_body_req = _schema_props(base_schema)
        _, cur_body_req = _schema_props(cur_schema)
        for prop in sorted(cur_body_req - base_body_req):
            breaks.append(f"new required requestBody property on {key}: {prop}")

        removed_2xx = _success_statuses(base_op) - _success_statuses(cur_op)
        for code in sorted(removed_2xx):
            breaks.append(f"removed success response on {key}: {code}")

    return breaks


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OpenAPI for breaking changes")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "openapi.snapshot.json",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate snapshot from live app (same as export_openapi.py)",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    if args.update:
        export_script = Path(__file__).with_name("export_openapi.py")
        # Re-exec export to avoid package-import coupling.
        import runpy

        sys.argv = [str(export_script), "--out", str(args.snapshot)]
        runpy.run_path(str(export_script), run_name="__main__")
        return 0

    if not args.snapshot.is_file():
        print(f"ERROR: missing snapshot {args.snapshot}", file=sys.stderr)
        print("Generate with: PYTHONPATH=. python scripts/export_openapi.py", file=sys.stderr)
        return 2

    from app.main import app

    current = app.openapi()
    baseline = _load(args.snapshot)
    breaks = find_breaking(baseline, current)

    if breaks:
        print("OpenAPI breaking changes detected:")
        for item in breaks:
            print(f"  - {item}")
        print()
        print("If intentional, regenerate the snapshot:")
        print("  PYTHONPATH=. python scripts/export_openapi.py")
        print("and commit backend/openapi.snapshot.json with the PR.")
        return 1

    print(
        f"OpenAPI breaking check OK "
        f"({len(_collect_ops(current))} operations vs snapshot {args.snapshot.name})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
