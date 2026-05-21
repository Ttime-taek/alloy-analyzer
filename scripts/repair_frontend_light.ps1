# Repair frontend build deps without deleting node_modules (safe for start_all)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$PortableNode = Join-Path $Root "tools\node22"
$npm = Join-Path $PortableNode "npm.cmd"
if (-not (Test-Path $npm)) { $npm = Join-Path $env:ProgramFiles "nodejs\npm.cmd" }
if (Test-Path $PortableNode) { $env:Path = "$PortableNode;$env:Path" }

function Test-DevMinimum {
    $min = @(
        "node_modules\vite\dist\node\cli.js",
        "node_modules\caniuse-lite\dist\lib\supported.js",
        "node_modules\@esbuild\win32-x64\esbuild.exe"
    )
    foreach ($rel in $min) {
        if (-not (Test-Path (Join-Path $Fe $rel))) { return $false }
    }
    return $true
}

if (-not (Test-DevMinimum)) {
    Write-Host "[repair] Dev minimum missing — running npm rebuild esbuild + optional packs..."
}

try { Add-MpPreference -ExclusionPath $Root -ErrorAction SilentlyContinue | Out-Null } catch {}

$nm = Join-Path $Fe "node_modules"
Get-ChildItem -Path $nm -Recurse -Include *.exe, *.node -ErrorAction SilentlyContinue |
    ForEach-Object { Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue }

Set-Location $Fe
if (-not (Test-Path (Join-Path $nm "caniuse-lite\dist\lib\supported.js"))) {
    & (Join-Path $Root "scripts\repair_caniuse_lite.ps1")
}
if (-not (Test-Path (Join-Path $nm "vite\package.json"))) {
    & (Join-Path $Root "scripts\repair_npm_pack.ps1") -Package "vite@5.4.21" -MarkerRel "vite\package.json"
}
& $npm rebuild esbuild --no-audit 2>&1 | Out-Null
if (-not (Test-Path (Join-Path $nm "@esbuild\win32-x64\esbuild.exe"))) {
    & $npm install esbuild@0.21.5 --no-save --no-audit 2>&1 | Out-Null
    & $npm rebuild esbuild --no-audit 2>&1 | Out-Null
}

if (Test-DevMinimum) {
    Write-Host "[repair] OK — run start_all.bat or npm run build in frontend/"
    exit 0
}
Write-Host "[repair] Still incomplete."
exit 1
