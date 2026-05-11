@echo off
REM ============================================================
REM  Music Spectrum Studio - setup script (Windows)
REM  Installs Python dependencies and confirms FFmpeg status.
REM ============================================================
SETLOCAL ENABLEDELAYEDEXPANSION
CD /D "%~dp0"

echo.
echo === Music Spectrum Studio: Setup ===
echo.

REM 1) Pastikan Python tersedia
where python >NUL 2>NUL
IF ERRORLEVEL 1 (
    echo [ERROR] Python tidak ditemukan di PATH.
    echo Silakan install Python 3.10+ dari https://www.python.org/downloads/
    pause
    EXIT /B 1
)

REM 2) Tampilkan versi
python --version

REM 3) Buat virtual environment (jika belum ada)
IF NOT EXIST ".venv" (
    echo Membuat virtual environment .venv ...
    python -m venv .venv
)

CALL ".venv\Scripts\activate.bat"

REM 4) Upgrade pip
python -m pip install --upgrade pip

REM 5) Install dependencies
echo Menginstall dependencies dari requirements.txt ...
pip install -r requirements.txt

REM 6) Status FFmpeg
echo.
where ffmpeg >NUL 2>NUL
IF ERRORLEVEL 1 (
    IF EXIST "bin\ffmpeg.exe" (
        echo [OK] FFmpeg tersedia di .\bin\ffmpeg.exe
    ) ELSE (
        echo [WARNING] FFmpeg belum terpasang.
        echo Anda dapat menginstall lewat tombol "Install FFmpeg" pada GUI,
        echo atau jalankan setup.bat lagi setelah install manual.
    )
) ELSE (
    echo [OK] FFmpeg ditemukan di PATH.
)

echo.
echo Setup selesai. Jalankan run.bat untuk membuka aplikasi.
pause
ENDLOCAL
