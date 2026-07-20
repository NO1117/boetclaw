#!/usr/bin/env bash
# Reproduce the main GitHub Actions CI gates locally (Linux/macOS).
# Real Provider / channel E2E is NOT included.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
FAILED=0
SKIP_E2E=0
SKIP_SECURITY=0

for arg in "$@"; do
  case "$arg" in
    --skip-e2e) SKIP_E2E=1 ;;
    --skip-security) SKIP_SECURITY=1 ;;
    -h|--help)
      echo "Usage: $0 [--skip-e2e] [--skip-security]"
      exit 0
      ;;
  esac
done

step() {
  local name="$1"; shift
  echo ""
  echo "==> $name"
  if "$@"; then
    echo "OK: $name"
  else
    echo "FAIL: $name"
    FAILED=$((FAILED + 1))
  fi
}

echo "BoetClaw local CI gates (PLAN-420)"
echo "Root: $ROOT"

cd "$BACKEND"
if [[ ! -x .venv/bin/python ]]; then
  echo "==> Creating backend/.venv"
  python3 -m venv .venv
fi
PY="$BACKEND/.venv/bin/python"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements-dev.txt
export PYTHONPATH="$BACKEND"

step "ruff check" "$PY" -m ruff check app tests scripts
step "mypy" "$PY" -m mypy app --config-file pyproject.toml
step "openapi breaking check" "$PY" scripts/check_openapi_breaking.py
step "pytest" "$PY" -m pytest -q

cd "$FRONTEND"
if [[ ! -d node_modules ]]; then
  echo "==> npm ci"
  npm ci || npm install
fi

step "npm test -- --run" npm test -- --run
step "npm run test:coverage" npm run test:coverage
step "npm run build" npm run build

if [[ "$SKIP_E2E" -eq 0 ]]; then
  step "playwright install chromium" npx playwright install chromium
  step "npm run test:e2e" npm run test:e2e
else
  echo "SKIP: E2E (--skip-e2e)"
fi

cd "$ROOT"
step "docker compose config" docker compose config --quiet

if [[ "$SKIP_SECURITY" -eq 0 ]]; then
  cd "$BACKEND"
  step "pip-audit" "$PY" -m pip_audit -r requirements.txt --progress-spinner off
  cd "$FRONTEND"
  step "npm audit (prod, high+)" npm audit --omit=dev --audit-level=high
else
  echo "SKIP: security (--skip-security)"
fi

cd "$ROOT"
echo ""
if [[ "$FAILED" -gt 0 ]]; then
  echo "Local CI finished with $FAILED failure(s)."
  exit 1
fi
echo "Local CI finished OK. Cloud GitHub Actions still requires a git remote + Actions enabled."
exit 0
