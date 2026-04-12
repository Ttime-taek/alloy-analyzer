@echo off
REM API server only (no Vite). Uses python or py.
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel% equ 0 (
  python api_server.py
  exit /b %errorlevel%
)
where py >nul 2>&1
if %errorlevel% equ 0 (
  py -3 api_server.py
  exit /b %errorlevel%
)
echo [ERROR] python or py not in PATH.
pause
exit /b 1
