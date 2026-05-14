#!/usr/bin/env bash
set -e
if [ ! -f "venv/bin/activate" ]; then
    echo "[ERROR] Virtual environment belum ada. Jalankan ./setup.sh terlebih dahulu."
    exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate
python -m verticlip "$@"
