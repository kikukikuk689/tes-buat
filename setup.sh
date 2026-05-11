#!/usr/bin/env bash
# Setup script for Linux / macOS users.
set -e
cd "$(dirname "$0")"

echo "=== Music Spectrum Studio: Setup ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 tidak ditemukan."
  exit 1
fi

python3 --version

if [ ! -d ".venv" ]; then
  echo "Membuat virtual environment .venv ..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  if [ -x "./bin/ffmpeg" ]; then
    echo "[OK] FFmpeg tersedia di ./bin/ffmpeg"
  else
    echo "[WARNING] FFmpeg belum terpasang."
    echo "Anda dapat menginstall lewat tombol 'Install FFmpeg' pada GUI,"
    echo "atau install via package manager (apt/brew)."
  fi
else
  echo "[OK] FFmpeg ditemukan: $(command -v ffmpeg)"
fi

echo
echo "Setup selesai. Jalankan ./run.sh untuk membuka aplikasi."
