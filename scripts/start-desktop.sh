#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="http://127.0.0.1:8000/app"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"
LOG_FILE="$ROOT_DIR/logs/desktop-server.log"

mkdir -p "$ROOT_DIR/logs"

if ! curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
  cd "$ROOT_DIR/backend"
  "$ROOT_DIR/backend/.venv/bin/alembic" upgrade head >/dev/null 2>&1 || true
  nohup "$ROOT_DIR/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 \
    >"$LOG_FILE" 2>&1 &

  for _ in $(seq 1 40); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
fi

if command -v google-chrome >/dev/null 2>&1; then
  exec google-chrome --app="$URL"
elif command -v chromium >/dev/null 2>&1; then
  exec chromium --app="$URL"
elif command -v chromium-browser >/dev/null 2>&1; then
  exec chromium-browser --app="$URL"
elif command -v firefox >/dev/null 2>&1; then
  exec firefox --new-window "$URL"
else
  exec xdg-open "$URL"
fi
