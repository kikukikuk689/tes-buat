@echo off
REM ---------------------------------------------------------------------------
REM  Snake Neon - one-time setup script for Windows.
REM  Creates a local virtual environment and installs the dependencies.
REM ---------------------------------------------------------------------------

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not found on PATH. Please install Python 3.9+ first.
    pause
    exit /b 1
)

if not exist "venv" (
    echo Creating virtual environment in "venv"...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Setup complete. Use run.bat to start the game.
pause
endlocal
