@echo off
setlocal
title MusicViz Studio

if not exist ".venv\Scripts\activate.bat" (
    echo [!] Virtual environment belum ada. Jalankan setup.bat dulu.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Tambah ffmpeg lokal ke PATH kalau ada
if exist "tools\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%CD%\tools\ffmpeg\bin;%PATH%"
)

python main.py %*

endlocal
