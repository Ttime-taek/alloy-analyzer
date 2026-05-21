@echo off
setlocal
pushd "%~dp0"
title Alloy Predictor API

echo.
echo  API: http://localhost:8000/
echo  Close this window to stop the server.
echo.

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
