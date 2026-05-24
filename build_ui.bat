@echo off
chcp 65001 >nul 2>&1
title Build UI
cd /d "%~dp0"

if not exist "%~dp0tools\node22\node.exe" (
  echo [ERROR] Portable Node not found.
  echo Run: scripts\setup_portable_node.ps1
  pause
  exit /b 1
)

if not exist "frontend\node_modules\vite\bin\vite.js" (
  echo [install] frontend dependencies...
  call "%~dp0scripts\fix_frontend_deps.cmd"
  if errorlevel 1 exit /b 1
)

echo [build] scripts\build_frontend.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_frontend.ps1"
if errorlevel 1 (
  echo.
  echo Build failed. See build-last.log in the repo root.
  echo Try: scripts\repair_frontend_light.ps1
  echo      scripts\fix_frontend_deps.cmd
  pause
  exit /b 1
)

echo.
echo Open in browser after starting API:
echo   http://localhost:8000/
echo.
pause
