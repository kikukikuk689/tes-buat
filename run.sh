#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "Virtual environment belum dibuat. Jalankan ./setup.sh dulu."
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m app.main "$@"
