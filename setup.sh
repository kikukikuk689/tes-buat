#!/usr/bin/env bash
set -e

echo "============================================================"
echo "  VertiClip Studio - Setup (Linux/macOS)"
echo "============================================================"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 tidak ditemukan. Install Python 3.10+ terlebih dahulu."
    exit 1
fi

PYVER=$(python3 --version 2>&1 | awk '{print $2}')
echo "[OK] Python terdeteksi: $PYVER"

if [ ! -d "venv" ]; then
    echo "[..] Membuat virtual environment ..."
    python3 -m venv venv
    echo "[OK] Virtual environment dibuat."
else
    echo "[OK] Virtual environment sudah ada."
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "[..] Upgrading pip ..."
python -m pip install --upgrade pip

echo "[..] Menginstall dependencies ..."
pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[WARN] FFmpeg belum terdeteksi. Install via package manager OS Anda,"
    echo "       atau gunakan tombol 'Install FFmpeg' dari dalam aplikasi (Windows)."
else
    echo "[OK] FFmpeg sudah terinstall."
fi

echo "============================================================"
echo "  Setup selesai! Jalankan ./run.sh untuk membuka aplikasi."
echo "============================================================"
