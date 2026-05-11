#!/usr/bin/env bash
# MusicViz Studio - Setup (Linux/Mac)
set -e
cd "$(dirname "$0")"

echo "==============================================="
echo "  MusicViz Studio - Setup"
echo "==============================================="

if ! command -v python3 >/dev/null 2>&1; then
    echo "[X] python3 tidak ditemukan. Install Python >= 3.10 dulu."
    exit 1
fi
echo "[v] Python: $(python3 --version)"

if [ ! -d ".venv" ]; then
    echo "[i] Membuat virtualenv .venv ..."
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip --quiet
python -m pip install --upgrade -r requirements.txt

if command -v ffmpeg >/dev/null 2>&1; then
    echo "[v] FFmpeg: $(ffmpeg -version | head -n1)"
else
    echo "[!] FFmpeg belum terinstall."
    echo "    Linux: sudo apt install ffmpeg"
    echo "    Mac:   brew install ffmpeg"
fi

echo "Setup selesai. Jalankan ./run.sh"
