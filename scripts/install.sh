#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
SKIP_FRONTEND="${SKIP_FRONTEND:-0}"

echo "==> BoetClaw install (Linux/macOS)"

cd "$BACKEND"
if ! python3 -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)'; then
  echo "BoetClaw backend requires Python 3.11-3.13. Please install Python 3.12/3.13 and retry." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "==> Creating Python virtual environment"
  python3 -m venv .venv
fi

echo "==> Installing backend dependencies"
"$BACKEND/.venv/bin/python" -m pip install --upgrade pip
"$BACKEND/.venv/bin/python" -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  echo "==> Initializing backend/.env from .env.example"
  cp .env.example .env
fi

if [ "$SKIP_FRONTEND" != "1" ]; then
  cd "$FRONTEND"
  echo "==> Installing frontend dependencies"
  npm install
fi

cd "$ROOT"
echo ""
echo "Install complete."
echo "Backend:  cd backend && .venv/bin/python run.py"
echo "Frontend: cd frontend && npm run dev"
