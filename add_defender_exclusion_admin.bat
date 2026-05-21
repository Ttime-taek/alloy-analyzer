@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM Already Administrator?
net session >nul 2>&1
if %errorlevel% equ 0 goto :run

REM Ask UAC (Yes on the popup)
echo Windows will ask for Administrator permission...
powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -ArgumentList 'ELEVATED'"
exit /b %errorlevel%

:run
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\add_defender_exclusion.ps1"
echo.
pause
