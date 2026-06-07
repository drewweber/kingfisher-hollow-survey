#!/bin/sh
# Nightly wrapper: sync new observations, refresh stats, rebuild the report.
# Invoked by launchd (com.kingfisher.inat.plist) or by hand.
set -e
cd "$(dirname "$0")"

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

TS=$(date "+%Y-%m-%d %H:%M:%S")
echo "=== run.sh start $TS ==="
"$PY" sync.py --all
"$PY" report.py
echo "=== run.sh done $(date '+%Y-%m-%d %H:%M:%S') ==="
