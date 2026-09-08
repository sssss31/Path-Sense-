#!/usr/bin/env bash
# One-command local runner (macOS/Linux). Windows: run.bat
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Python 3.12 not found. Install it and rerun."; exit 1; }
exec "$PY" scripts/bootstrap.py "$@"
