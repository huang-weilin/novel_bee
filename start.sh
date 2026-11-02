#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_PY=".venv/bin/python"
PYTHON_CHECK='import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'

find_python() {
  local candidate
  for candidate in "${PYTHON:-}" python3.12 python3.11 python3; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c "$PYTHON_CHECK" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if [ -x "$VENV_PY" ]; then
  if ! "$VENV_PY" -c "$PYTHON_CHECK" >/dev/null 2>&1; then
    echo "ERROR: The existing .venv uses Python older than 3.11."
    echo "Delete the .venv folder and run ./start.sh again."
    exit 1
  fi
else
  echo "[1/3] Looking for Python 3.11 or newer..."
  if ! PYTHON_BIN="$(find_python)"; then
    echo "ERROR: Python 3.11 or newer was not found."
    echo "Install it from https://www.python.org/downloads/ and run ./start.sh again."
    echo "You can also set PYTHON=/path/to/python3.12 to choose an interpreter."
    exit 1
  fi
  echo "[1/3] Creating the local Python environment..."
  "$PYTHON_BIN" -m venv .venv
fi

echo "[2/3] Installing project dependencies..."
"$VENV_PY" -m pip install -e . --quiet

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo
  echo "Created .env. Open the web page and click \"AI Settings\" to enter your key."
  echo "The key is stored only in this folder and is never committed."
  echo
fi

echo "[3/3] Starting the local web app..."
echo "The web app will print its address below (default: http://127.0.0.1:8000)."
echo "Press Ctrl+C in this window to stop the server."
exec "$VENV_PY" -m novel_pipeline.server "$@"
