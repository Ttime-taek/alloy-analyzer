# Fix missing/corrupt caniuse-lite (npm extract often drops this on Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$npm = Join-Path $Root "tools\node22\npm.cmd"
if (-not (Test-Path $npm)) { $npm = Join-Path $env:ProgramFiles "nodejs\npm.cmd" }
$marker = Join-Path $Fe "node_modules\caniuse-lite\dist\lib\supported.js"
if (Test-Path $marker) { exit 0 }

Write-Host "[repair] Installing caniuse-lite via npm pack..."
Set-Location $Fe
$ver = "1.0.30001784"
$tgz = Join-Path $env:TEMP "caniuse-lite-$ver.tgz"
if (-not (Test-Path $tgz)) {
    & $npm pack "caniuse-lite@$ver" --pack-destination $env:TEMP | Out-Null
}
$dest = Join-Path $Fe "node_modules\caniuse-lite"
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
New-Item -ItemType Directory -Force -Path $dest | Out-Null
tar -xzf $tgz -C $dest --strip-components=1
if (-not (Test-Path $marker)) { throw "caniuse-lite repair failed" }
Write-Host "[repair] caniuse-lite OK"
