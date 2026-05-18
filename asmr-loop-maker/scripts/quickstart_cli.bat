@echo off
REM One-shot: setup virtualenv + install dependencies + run a batch render from
REM input\ into output\. Override defaults with INPUT, OUTPUT, HOURS, CROSSFADE.
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

if "%INPUT%"=="" set "INPUT=input"
if "%OUTPUT%"=="" set "OUTPUT=output"
if "%HOURS%"=="" set "HOURS=1"
if "%CROSSFADE%"=="" set "CROSSFADE=0.8"

python main.py --input "%INPUT%" --output "%OUTPUT%" --hours %HOURS% --crossfade %CROSSFADE% --batch
popd
endlocal
