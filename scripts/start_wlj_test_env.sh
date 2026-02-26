#!/usr/bin/env bash
# ==============================================================================
# File: scripts/start_wlj_test_env.sh
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bootstrap script to start the WLJ dev server and open UI tests
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
# Updated: 2026-02-26 — Hardened: venv enforcement, dj-stripe version check
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

# ── Locate and activate virtualenv (REQUIRED) ────────────────────────────────
# Search PROJECT_ROOT first, then the git main worktree root (for worktree checkouts)
VENV_FOUND=0
SEARCH_ROOTS=("$PROJECT_ROOT")
GIT_MAIN_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's|/\.git$||' || true)"
if [ -n "$GIT_MAIN_ROOT" ] && [ "$GIT_MAIN_ROOT" != "$PROJECT_ROOT" ]; then
    SEARCH_ROOTS+=("$GIT_MAIN_ROOT")
fi

for SEARCH_ROOT in "${SEARCH_ROOTS[@]}"; do
    for VENV_DIR in venv .venv env; do
        if [ -f "$SEARCH_ROOT/$VENV_DIR/bin/activate" ]; then
            echo "==> Activating virtualenv: $SEARCH_ROOT/$VENV_DIR"
            # shellcheck disable=SC1091
            source "$SEARCH_ROOT/$VENV_DIR/bin/activate"
            VENV_FOUND=1
            break 2
        fi
    done
done

if [ "$VENV_FOUND" -eq 0 ]; then
    echo "ERROR: No virtualenv found (checked venv, .venv, env). Cannot proceed without venv."
    exit 1
fi

# ── Validate environment: venv path + dj-stripe version ─────────────────────
echo "==> Validating environment..."
python3 - <<'PYCHECK'
import sys
import importlib.metadata

exe = sys.executable
print(f"    Python executable: {exe}")

# Must be running from project venv, not system Python
if "/venv/" not in exe and "/.venv/" not in exe and "/env/" not in exe:
    raise SystemExit(
        "ERROR: Python executable is not inside the project virtualenv.\n"
        f"       Found: {exe}\n"
        "       Expected path to contain /venv/, /.venv/, or /env/.\n"
        "       Aborting to prevent version mismatches."
    )

try:
    version = importlib.metadata.version("dj-stripe")
    print(f"    dj-stripe version: {version}")
except importlib.metadata.PackageNotFoundError:
    raise SystemExit(
        "ERROR: dj-stripe is not installed in this virtualenv.\n"
        "       Run: pip install dj-stripe==2.10.3"
    )

if version != "2.10.3":
    raise SystemExit(
        f"ERROR: dj-stripe version mismatch.\n"
        f"       Installed: {version}\n"
        f"       Required:  2.10.3\n"
        f"       Run: pip install dj-stripe==2.10.3"
    )

print("    Environment OK")
PYCHECK

echo "==> Environment validated."

# ── Run migrations ───────────────────────────────────────────────────────────
echo "==> Running migrations..."
if ! python3 manage.py migrate --noinput 2>&1; then
    echo ""
    echo "ERROR: Migration failed. Fix the issue above before starting the server."
    exit 1
fi
echo "==> Migrations complete."

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
        if curl -s -o /dev/null -w '' "http://127.0.0.1:$PORT/" 2>/dev/null; then
            echo " ready!"
            break
        fi
        echo -n "."
        sleep 1
    done

    if ! curl -s -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then
        echo " TIMEOUT — server did not start within 30s."
        echo "    Check logs above for errors."
        kill "$SERVER_PID" 2>/dev/null || true
        exit 1
    fi

    # Trap to clean up server on exit
    trap 'echo "==> Shutting down server (PID $SERVER_PID)..."; kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM
fi

# ── Open browser ─────────────────────────────────────────────────────────────
URL="http://127.0.0.1:$PORT/admin-console/ui-tests/"

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
echo "  Server:   http://127.0.0.1:$PORT/"
echo "  UI Tests: $URL"
echo ""
echo "  Select a module to run from the Admin"
echo "  Console — tests do NOT auto-run."
echo ""
echo "  Press Ctrl+C to stop"
echo "============================================"

# Keep script alive (wait for server process)
if [ "$SKIP_SERVER" -eq 0 ]; then
    wait "$SERVER_PID"
fi
