@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
if errorlevel 1 (
  echo [ERROR] Cannot cd to repo root from %~dp0
  exit /b 1
)

set "ROOT=%CD%"
set "NODE_DIR=%ROOT%\tools\node22"
set "NODE=%NODE_DIR%\node.exe"
set "NPM=%NODE_DIR%\npm.cmd"
set "FE=%ROOT%\frontend"
set "VITE=%FE%\node_modules\vite\bin\vite.js"
set "ESBUILD=%FE%\node_modules\@esbuild\win32-x64\esbuild.exe"
set "LOG=%ROOT%\build-last.log"

if not exist "%NODE%" (
  echo [ERROR] Portable Node missing: %NODE%
  echo Run: scripts\setup_portable_node.ps1
  exit /b 1
)
if not exist "%VITE%" (
  echo [ERROR] Vite not installed. Run: scripts\fix_frontend_deps.cmd
  exit /b 1
)
if not exist "%ESBUILD%" (
  echo [WARN] esbuild binary missing - running repair_frontend_light.ps1 ...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\repair_frontend_light.ps1"
  if not exist "%ESBUILD%" (
    echo [ERROR] esbuild still missing after repair. Run: scripts\fix_frontend_deps.cmd
    exit /b 1
  )
)

set "PATH=%NODE_DIR%;%PATH%"
set VITE_ESLINT_CHECK=0
cd /d "%FE%"
echo [build] npm run build
call "%NPM%" run build 1>"%LOG%" 2>&1
set EC=%ERRORLEVEL%
if exist "%LOG%" type "%LOG%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] Vite build failed exit %EC%. See: %LOG%
  exit /b %EC%
)
echo.
echo [OK] Built: frontend\dist
exit /b 0
