# One-shot prep for /gstack-design-review (Windows): compiled browse CLI + URL reminder.
$ErrorActionPreference = 'Stop'
$gstackRoot = Join-Path $env:USERPROFILE '.cursor/skills/gstack'
$browseExe = Join-Path $gstackRoot 'browse/dist/browse.exe'

if (-not (Test-Path $browseExe)) {
    if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
        Write-Error 'Install Bun first: https://bun.sh — then re-run this script.'
    }
    Write-Host 'Compiling gstack browse (bun --compile)...'
    Push-Location $gstackRoot
    try {
        bun build --compile browse/src/cli.ts --outfile browse/dist/browse
        bun build --compile browse/src/find-browse.ts --outfile browse/dist/find-browse
    }
    finally {
        Pop-Location
    }
}

Write-Host "browse: $browseExe"
if (Test-Path $browseExe) { Write-Host '(browse.exe OK)' } else { Write-Host '(WARN: browse.exe still missing)' }

Write-Host ''
Write-Host '1) Terminal A - API (optional):  python api_server.py'
Write-Host '2) Terminal B - frontend:       cd frontend; npm run dev'
Write-Host '3) Open / tell agents URL:      http://127.0.0.1:5173/'
Write-Host '4) Run /gstack-design-review with that URL (master branch).'
