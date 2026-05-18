@echo off
REM ---------------------------------------------------------------------------
REM  Snake Neon - launcher for Windows.
REM  Activates the virtual environment if present and starts the game.
REM ---------------------------------------------------------------------------

setlocal

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] The game exited with an error. Did you run setup.bat first?
    pause
)

endlocal
