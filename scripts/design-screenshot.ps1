# Design audit: load page then screenshot (gstack browse).
# Run Vite first: npm run dev (port 5173). FINDING-001: wait --load before capture.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$browse = Join-Path $env:USERPROFILE ".cursor\skills\gstack\browse\dist\browse.exe"
if (-not (Test-Path $browse)) {
  Write-Error "browse.exe not found: $browse"
}

$outDir = Join-Path $root "screenshots-design-audit"
if (-not (Test-Path $outDir)) {
  New-Item -ItemType Directory -Path $outDir | Out-Null
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $outDir "design-audit-$ts.png"

& $browse goto "http://127.0.0.1:5173/"
& $browse wait --load
& $browse screenshot $out

Write-Host "Saved: $out"
