@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul
if not errorlevel 1 goto PY_LAUNCHER
python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>nul
if not errorlevel 1 goto PY_PLAIN

echo Grand Mobile Support needs Python 3.12 or newer.
echo Install Python from https://www.python.org/downloads/windows/
echo Select Add Python to PATH during installation, then run START_WINDOWS.bat again.
pause
exit /b 1

:PY_LAUNCHER
py -3 -m scripts.windows_bootstrap
if errorlevel 1 goto FAILED
exit /b 0

:PY_PLAIN
python -m scripts.windows_bootstrap
if errorlevel 1 goto FAILED
exit /b 0

:FAILED
echo.
echo Startup stopped. Please check the message above.
pause
exit /b 1
