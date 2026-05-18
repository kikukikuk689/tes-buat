@echo off
REM Example: run a batch render from input\ into output\ for 1 hour with a 0.8s crossfade.
setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
pushd "%PROJECT_DIR%"

if "%VENV_DIR%"=="" set VENV_DIR=%CD%\.venv
if exist "%VENV_DIR%\Scripts\activate.bat" call "%VENV_DIR%\Scripts\activate.bat"

if "%INPUT%"=="" set INPUT=input
if "%OUTPUT%"=="" set OUTPUT=output
if "%HOURS%"=="" set HOURS=1
if "%CROSSFADE%"=="" set CROSSFADE=0.8

python main.py --input "%INPUT%" --output "%OUTPUT%" --hours %HOURS% --crossfade %CROSSFADE% --batch
popd
endlocal
