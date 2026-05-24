# Prep gstack browse on Windows when Playwright headless_shell times out.
# Usage: .\scripts\prep_qa_browse.ps1
# Then in another terminal: browse.exe goto http://127.0.0.1:8000/
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Profile = Join-Path $Root ".gstack\chrome-browse-profile"
$BrowseExe = Join-Path $env:USERPROFILE ".cursor\skills\gstack\browse\dist\browse.exe"
if (-not (Test-Path $BrowseExe)) {
    $BrowseExe = Join-Path $env:USERPROFILE ".claude\skills\gstack\browse\dist\browse.exe"
}

$env:BROWSE_STATE_FILE = Join-Path $Root ".gstack\browse.json"
$env:PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL = "0"
$chrome = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
if (Test-Path $chrome) { $env:GSTACK_CHROMIUM_PATH = $chrome }

Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
if (Test-Path $Profile) { Remove-Item -Recurse -Force $Profile -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $Profile | Out-Null

Start-Process -FilePath $chrome -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$Profile",
    "--no-first-run",
    "http://127.0.0.1:8000/"
) | Out-Null

Write-Host "BROWSE_STATE_FILE=$($env:BROWSE_STATE_FILE)"
Write-Host "PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0"
if ($env:GSTACK_CHROMIUM_PATH) { Write-Host "GSTACK_CHROMIUM_PATH=$($env:GSTACK_CHROMIUM_PATH)" }
Write-Host ""
Write-Host "Chrome started on CDP :9222. Wait ~5s, then:"
Write-Host "  `$env:BROWSE_STATE_FILE = '$($env:BROWSE_STATE_FILE)'"
Write-Host "  & '$BrowseExe' goto http://127.0.0.1:8000/"
Write-Host ""
Write-Host "If browse still fails, use: py -3 scripts\qa_ui_selenium.py"
