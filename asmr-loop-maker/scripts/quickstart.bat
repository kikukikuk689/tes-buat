@echo off
REM One-shot: setup virtualenv + install dependencies + launch the Streamlit UI.
REM Useful for first-time users who just want to double-click and go.
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
pushd "%PROJECT_DIR%"

call "%SCRIPT_DIR%setup.bat"
if errorlevel 1 (
  popd
  exit /b 1
)

if "%VENV_DIR%"=="" set "VENV_DIR=%CD%\.venv"
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
  popd
  exit /b 1
)

streamlit run app\ui.py %*
popd
endlocal
