@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0..\frontend"
echo [install_frontend] npm ci ...
call "%ProgramFiles%\nodejs\npm.cmd" ci --no-audit --no-fund
if errorlevel 1 (
  echo [install_frontend] npm ci failed, trying npm install ...
  call "%ProgramFiles%\nodejs\npm.cmd" install --no-audit --no-fund
)
echo [install_frontend] Unblock native binaries...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%CD%\node_modules' -Recurse -Include *.exe,*.node -ErrorAction SilentlyContinue | ForEach-Object { Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue }"
call "%ProgramFiles%\nodejs\npm.cmd" rebuild esbuild --no-audit
if not exist "node_modules\vite\bin\vite.js" (
  echo [ERROR] vite not installed. Install Node 22 LTS, then retry.
  pause
  exit /b 1
)
echo [install_frontend] OK
pause
