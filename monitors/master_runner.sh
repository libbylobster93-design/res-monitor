#!/usr/bin/env bash
# Master runner — checks all platforms and sends Telegram alert if slots found.
set -euo pipefail

PYTHON=/Users/lisalobster/.local/bin/python3.12
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Res Monitor Run: $(date '+%Y-%m-%d %H:%M PT') ==="

cd "$SCRIPT_DIR/.."
"$PYTHON" monitors/run_checks.py
