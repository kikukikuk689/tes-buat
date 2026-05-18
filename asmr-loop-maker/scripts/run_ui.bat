@echo off
REM Launch the Streamlit UI for ASMR Seamless Loop Maker.
setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
pushd "%PROJECT_DIR%"

if "%VENV_DIR%"=="" set VENV_DIR=%CD%\.venv
if exist "%VENV_DIR%\Scripts\activate.bat" call "%VENV_DIR%\Scripts\activate.bat"

streamlit run app\ui.py %*
popd
endlocal
