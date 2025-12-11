#!/bin/bash
set -e

# Defaults (safe fallback if env vars are missing)
WORKERS=${UVICORN_WORKERS:-1}
TIMEOUT=${UVICORN_TIMEOUT:-30}

echo "--- 🦄 Starting Uvicorn ---"
echo "Workers: $WORKERS | Timeout: $TIMEOUT"

# 'exec' is CRITICAL.
# It replaces the shell process with Uvicorn, ensuring
# Ctrl+C (SIGTERM) signals are passed directly to the app.
exec uvicorn verve_backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "$WORKERS" \
  --timeout-keep-alive "$TIMEOUT"
