@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "PYTHON_CMD="

if exist "%VENV_PY%" goto :check_venv

echo [1/3] Looking for Python 3.11 or newer...
for %%C in ("py -3.12" "py -3.11" "py -3" "python") do (
  if not defined PYTHON_CMD (
    %%~C -c "import sys;raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%%~C"
  )
)
if not defined PYTHON_CMD goto :no_python

echo [1/3] Creating the local Python environment...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto :error

:check_venv
"%VENV_PY%" -c "import sys;raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: The existing .venv uses Python older than 3.11.
  echo Delete the .venv folder and run start.bat again.
  echo.
  pause
  exit /b 1
)

echo [2/3] Installing project dependencies...
"%VENV_PY%" -m pip install -e . --quiet
if errorlevel 1 goto :error

if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo.
  echo Created .env. Open the web page and click "AI Settings" to enter your key.
  echo The key is stored only in this folder and is never committed.
  echo.
)

echo [3/3] Starting the local web app...
echo The web app will print its address below (default: http://127.0.0.1:8000).
echo Press Ctrl+C in this window to stop the server.
"%VENV_PY%" -m novel_pipeline.server %*
if errorlevel 1 goto :error
goto :end

:no_python
echo.
echo ERROR: Python 3.11 or newer was not found.
echo Download it from https://www.python.org/downloads/
echo During installation, tick "Add python.exe to PATH", then run start.bat again.
echo.
pause
exit /b 1

:error
echo.
echo Start failed. Read the message above, then press any key to close.
pause
:end
endlocal
