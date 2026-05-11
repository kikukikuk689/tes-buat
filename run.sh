#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "[!] Jalankan setup.sh dulu."
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
exec python main.py "$@"
