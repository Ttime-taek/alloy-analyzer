@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."
echo [fix] Repairing frontend build (UI served at http://localhost:8000/)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_frontend.ps1"
if errorlevel 1 (
  echo.
  echo If repair failed, run as Admin: add_defender_exclusion_admin.bat
  echo Then run this script again.
  pause
  exit /b 1
)
echo.
echo OK. Run: start_all.bat
pause
