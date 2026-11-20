#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "A iniciar J.A.R.V.I.S. (Backend + Frontend)..."
trap 'kill 0' EXIT

(
  cd "$ROOT_DIR/backend"
  source .venv/bin/activate
  alembic upgrade head
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &

(
  cd "$ROOT_DIR/frontend"
  npm run dev
) &

wait
