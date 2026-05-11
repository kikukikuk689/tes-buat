@echo off
setlocal ENABLEDELAYEDEXPANSION
title MusicViz Studio - Setup
color 0B

echo ===============================================
echo   MusicViz Studio - Setup
echo ===============================================
echo.

REM --- Cek Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python tidak ditemukan di PATH.
    echo     Silakan install Python ^>= 3.10 dari https://www.python.org/downloads/
    echo     Saat install centang "Add Python to PATH".
    pause
    exit /b 1
)

for /f "tokens=2" %%a in ('python --version 2^>^&1') do set PYVER=%%a
echo [v] Python terdeteksi: %PYVER%

REM --- Buat venv ---
if not exist ".venv\Scripts\activate.bat" (
    echo [i] Membuat virtual environment di .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Gagal membuat venv.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo [i] Upgrade pip ...
python -m pip install --upgrade pip --quiet

echo [i] Install dependencies (customtkinter, numpy, Pillow) ...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo [X] Install dependencies gagal.
    pause
    exit /b 1
)

REM --- Cek FFmpeg ---
where ffmpeg >nul 2>&1
if errorlevel 1 (
    if exist "tools\ffmpeg\bin\ffmpeg.exe" (
        echo [v] FFmpeg lokal tersedia di tools\ffmpeg\bin
    ) else (
        echo [!] FFmpeg belum terinstall.
        echo     Anda bisa install nanti dari dalam aplikasi
        echo     (tombol "Install FFmpeg Online" di status bar).
    )
) else (
    echo [v] FFmpeg sudah terinstall di sistem.
)

echo.
echo ===============================================
echo   Setup selesai. Jalankan run.bat untuk mulai.
echo ===============================================
echo.
pause
endlocal
