@echo off
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel% equ 0 (
  python regression_check.py
  exit /b %errorlevel%
)
where py >nul 2>&1
if %errorlevel% equ 0 (
  py -3 regression_check.py
  exit /b %errorlevel%
)
echo [ERROR] python or py not found in PATH.
exit /b 1

