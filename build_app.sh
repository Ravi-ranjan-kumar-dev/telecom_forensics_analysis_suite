#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
exec .venv/bin/python tools/build_desktop.py --install
