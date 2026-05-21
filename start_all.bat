@echo off

setlocal

pushd "%~dp0"

title Alloy Predictor

echo.

echo  Starting API + UI on http://localhost:8000/

echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_all.ps1"

set EC=%ERRORLEVEL%

popd

endlocal

if not "%EC%"=="0" pause

exit /b %EC%

