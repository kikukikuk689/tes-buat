#!/usr/bin/env bash
# Set up a Python virtual environment and install dependencies for the
# ASMR Seamless Loop Maker on macOS/Linux.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"

cd "$PROJECT_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "[setup] Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "[setup] Upgrading pip"
python -m pip install --upgrade pip

echo "[setup] Installing requirements"
python -m pip install -r requirements.txt

echo
echo "[setup] Done. Activate the environment with:"
echo "  source \"$VENV_DIR/bin/activate\""
echo
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: FFmpeg tidak ditemukan di PATH."
  echo "         Install FFmpeg sebelum menjalankan aplikasi:"
  echo "         macOS:   brew install ffmpeg"
  echo "         Ubuntu:  sudo apt-get install -y ffmpeg"
fi
