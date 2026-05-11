@echo off
REM ============================================================
REM  Music Spectrum Studio - launcher (Windows)
REM ============================================================
CD /D "%~dp0"

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment belum dibuat.
    echo Silakan jalankan setup.bat terlebih dahulu.
    pause
    EXIT /B 1
)

CALL ".venv\Scripts\activate.bat"
python -m app.main %*
