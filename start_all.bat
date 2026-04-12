@echo off
REM Loads full Machine+User PATH (like new CMD) then runs Vite + API. Use if double-click failed before.
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
if errorlevel 1 pause
