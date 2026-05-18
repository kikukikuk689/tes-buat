@echo off
REM Set up a Python virtual environment and install dependencies for the
REM ASMR Seamless Loop Maker on Windows.
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
pushd "%PROJECT_DIR%"

if "%PYTHON_BIN%"=="" set "PYTHON_BIN=python"
if "%VENV_DIR%"=="" set "VENV_DIR=%CD%\.venv"

if not exist "%VENV_DIR%" (
  echo [setup] Creating virtual environment at %VENV_DIR%
  %PYTHON_BIN% -m venv "%VENV_DIR%"
  if errorlevel 1 goto :error
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto :error

echo [setup] Upgrading pip
python -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [setup] Installing requirements
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo WARNING: FFmpeg tidak ditemukan di PATH.
  echo          Install FFmpeg dan pastikan bisa dipanggil dari Command Prompt.
)

echo.
echo [setup] Done. Activate the environment with:
echo   call "%VENV_DIR%\Scripts\activate.bat"
popd
exit /b 0

:error
echo [setup] Failed.
popd
exit /b 1
