@echo off
setlocal enabledelayedexpansion
title VertiClip Studio - Setup

echo ============================================================
echo   VertiClip Studio - Setup
echo ============================================================
echo.

REM ---- Check Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python tidak ditemukan di PATH.
    echo Silakan install Python 3.10+ dari https://www.python.org/downloads/
    echo Pastikan centang "Add Python to PATH" saat install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set "PYVER=%%a"
echo [OK] Python terdeteksi: %PYVER%
echo.

REM ---- Create virtual environment ----
if not exist "venv\" (
    echo [..] Membuat virtual environment ...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Gagal membuat venv. Pastikan modul venv tersedia.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment dibuat.
) else (
    echo [OK] Virtual environment sudah ada.
)
echo.

REM ---- Activate venv and install deps ----
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Gagal mengaktifkan venv.
    pause
    exit /b 1
)

echo [..] Upgrading pip ...
python -m pip install --upgrade pip
echo.

echo [..] Menginstall dependencies dari requirements.txt ...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Gagal install dependencies.
    pause
    exit /b 1
)
echo.

REM ---- FFmpeg check ----
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [WARN] FFmpeg belum terdeteksi di system PATH.
    echo Anda bisa install FFmpeg langsung dari aplikasi
    echo melalui tombol "Install FFmpeg" pada status bar.
) else (
    echo [OK] FFmpeg sudah terinstall.
)
echo.

echo ============================================================
echo   Setup selesai! Jalankan run.bat untuk membuka aplikasi.
echo ============================================================
echo.
pause
endlocal
