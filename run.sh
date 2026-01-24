#!/bin/bash
set -e

# Defaults (safe fallback if env vars are missing)
WORKERS=${UVICORN_WORKERS:-1}
TIMEOUT=${UVICORN_TIMEOUT:-30}

# -----------------------------------------------------
# 1. Database Migrations
# -----------------------------------------------------
echo "--- 🔄 Running Database Migrations ---"
# We are in the venv (via Dockerfile PATH), so we can run alembic directly.
alembic upgrade head

# -----------------------------------------------------
# 2. Admin User Setup (Conditional)
# -----------------------------------------------------
if [ -n "$ADMIN_PASSWORD" ]; then
  echo "--- 👤 Admin Password set. Ensuring admin ($ADMIN_EMAIL) exists ---"
  if [ -z "$ADMIN_EMAIL" ]; then
    echo "❌ ERROR: ADMIN_PASSWORD is set, but ADMIN_EMAIL is missing."
    echo "   You must provide both variables to create an admin user."
    exit 1
  fi

  python -m verve_backend.cli.create_admin_user \
    --password "$ADMIN_PASSWORD" \
    --email "$ADMIN_EMAIL"

else
  echo "--- ⏩ ADMIN_PASSWORD not set. Skipping admin check. ---"
fi

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
