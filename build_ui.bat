@echo off
chcp 65001 >nul 2>&1
title Build UI
cd /d "%~dp0"

set "NODE_DIR=%~dp0tools\node22"
set "NPM=%NODE_DIR%\npm.cmd"
if not exist "%NPM%" (
  echo [ERROR] Run scripts\setup_portable_node.ps1 first.
  pause
  exit /b 1
)
set "PATH=%NODE_DIR%;%PATH%"
set "VITE_ESLINT_CHECK=0"

if not exist "frontend\node_modules\vite\bin\vite.js" (
  echo [install] frontend dependencies...
  call "%~dp0scripts\fix_frontend_deps.cmd"
  if errorlevel 1 exit /b 1
)

cd /d "%~dp0frontend"
echo [build] npm run build ...
call "%NPM%" run build
if errorlevel 1 (
  echo [ERROR] build failed
  pause
  exit /b 1
)

echo.
echo [OK] Built: frontend\dist
echo Open in browser (API must be running):
echo   http://localhost:8000/
echo   http://192.168.82.215:8000/
echo.
pause
