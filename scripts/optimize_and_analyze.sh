#!/usr/bin/env bash
set -euo pipefail

# Cron-friendly wrapper to run DB ANALYZE and PRAGMA optimize for Mercator
# Usage: run from repo root or via CI: ./scripts/optimize_and_analyze.sh

export PYTHONPATH=. 

echo "Running optimize_sqlite.py..."
python3 scripts/optimize_sqlite.py

echo "Done."
