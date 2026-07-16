#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "[-] Project virtual environment not found."
    echo "    Expected: $PYTHON_BIN"
    echo ""
    echo "Fix:"
    echo "    python3 -m venv .venv"
    echo "    source .venv/bin/activate"
    echo "    pip install -r requirements.txt"
    exit 1
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -u main.py "$@"
