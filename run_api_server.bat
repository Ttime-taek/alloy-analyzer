@echo off
setlocal
pushd "%~dp0"
title Alloy Predictor API

echo.
echo  API: http://localhost:8000/
echo  Close this window to stop the server.
echo.

if exist "scripts\build_frontend.ps1" (
  echo [UI] Building frontend\dist ...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\build_frontend.ps1"
  if errorlevel 1 (
    echo [WARN] UI build failed. Run build_ui.bat manually, then restart this window.
  )
) else (
  if not exist "frontend\dist\index.html" (
    echo [WARN] frontend\dist missing. Run build_ui.bat before using the web UI.
  )
)

where py >nul 2>&1
if %errorlevel% equ 0 (
  py -3 api_server.py
  set EC=%errorlevel%
  goto done
)

where python >nul 2>&1
if %errorlevel% equ 0 (
  python api_server.py
  set EC=%errorlevel%
  goto done
)

echo [ERROR] Python not found. Install Python 3 and run again.
set EC=1
pause

:done
popd
endlocal
exit /b %EC%
