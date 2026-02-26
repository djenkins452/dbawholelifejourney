#!/usr/bin/env bash
# ==============================================================================
# File: scripts/start_wlj_test_env.sh
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bootstrap script to start the WLJ dev server and open UI tests
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
#
# Usage:
#   ./scripts/start_wlj_test_env.sh          # Start server + open UI tests page
#   ./scripts/start_wlj_test_env.sh --no-open # Start server without opening browser
# ==============================================================================
set -euo pipefail

# ── Auto-detect project root ─────────────────────────────────────────────────
# Walk up from this script's location until we find manage.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
while [ "$PROJECT_ROOT" != "/" ]; do
    [ -f "$PROJECT_ROOT/manage.py" ] && break
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done

if [ ! -f "$PROJECT_ROOT/manage.py" ]; then
    echo "ERROR: Could not find manage.py. Run this script from within the WLJ project."
    exit 1
fi

echo "==> Project root: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# ── Locate and activate virtualenv ───────────────────────────────────────────
VENV_FOUND=0
for VENV_DIR in venv .venv env; do
    if [ -f "$PROJECT_ROOT/$VENV_DIR/bin/activate" ]; then
        echo "==> Activating virtualenv: $VENV_DIR"
        # shellcheck disable=SC1091
        source "$PROJECT_ROOT/$VENV_DIR/bin/activate"
        VENV_FOUND=1
        break
    fi
done

if [ "$VENV_FOUND" -eq 0 ]; then
    echo "WARNING: No virtualenv found (checked venv, .venv, env). Using system Python."
fi

echo "==> Python: $(python3 --version 2>&1) at $(which python3)"

# ── Run migrations if needed ─────────────────────────────────────────────────
echo "==> Checking for pending migrations..."
PENDING=$(python3 manage.py showmigrations --plan 2>/dev/null | grep '\[ \]' | head -5 || true)
if [ -n "$PENDING" ]; then
    echo "==> Applying pending migrations..."
    python3 manage.py migrate --run-syncdb 2>&1 | tail -5
else
    echo "==> All migrations up to date."
fi

# ── Check if port 8000 is already in use ─────────────────────────────────────
PORT=8000
if lsof -ti :"$PORT" >/dev/null 2>&1; then
    echo "==> Port $PORT already in use. Server may already be running."
    echo "    PIDs on port $PORT: $(lsof -ti :$PORT | tr '\n' ' ')"
    echo "    Opening browser to existing server..."
    SKIP_SERVER=1
else
    SKIP_SERVER=0
fi

# ── Start Django dev server ──────────────────────────────────────────────────
if [ "$SKIP_SERVER" -eq 0 ]; then
    echo "==> Starting Django dev server on port $PORT..."
    python3 manage.py runserver "$PORT" &
    SERVER_PID=$!

    # Wait for server to be ready
    echo -n "==> Waiting for server"
    for i in $(seq 1 30); do
        if curl -s -o /dev/null -w '' "http://localhost:$PORT/" 2>/dev/null; then
            echo " ready!"
            break
        fi
        echo -n "."
        sleep 1
    done

    if ! curl -s -o /dev/null "http://localhost:$PORT/" 2>/dev/null; then
        echo " TIMEOUT — server did not start within 30s."
        echo "    Check logs above for errors."
        kill "$SERVER_PID" 2>/dev/null || true
        exit 1
    fi

    # Trap to clean up server on exit
    trap 'echo "==> Shutting down server (PID $SERVER_PID)..."; kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM
fi

# ── Open browser ─────────────────────────────────────────────────────────────
URL="http://localhost:$PORT/admin-console/ui-tests/"

if [[ "${1:-}" != "--no-open" ]]; then
    echo "==> Opening $URL"
    if command -v open >/dev/null 2>&1; then
        open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL"
    else
        echo "    Could not auto-open browser. Navigate to: $URL"
    fi
else
    echo "==> Server running at: $URL"
fi

# ── Status ───────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  WLJ Test Environment Running"
echo "  Server:  http://localhost:$PORT/"
echo "  UI Tests: $URL"
echo "  Press Ctrl+C to stop"
echo "============================================"

# Keep script alive (wait for server process)
if [ "$SKIP_SERVER" -eq 0 ]; then
    wait "$SERVER_PID"
fi
