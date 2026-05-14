@echo off
setlocal
title VertiClip Studio

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment belum ada.
    echo Jalankan setup.bat terlebih dahulu.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python -m verticlip
endlocal
