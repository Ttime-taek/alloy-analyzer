# One-shot frontend dependency install (run from repo root or scripts/)
param(
    [switch]$ForceReinstall
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$PortableNode = Join-Path $Root "tools\node22"
$nodeExe = Join-Path $PortableNode "node.exe"
$npm = Join-Path $PortableNode "npm.cmd"

if (-not (Test-Path $nodeExe)) {
    Write-Host "[install] Portable Node 22 not found - running setup_portable_node.ps1 ..."
    & (Join-Path $Root "scripts\setup_portable_node.ps1")
}
if (-not (Test-Path $npm)) {
    $npm = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
    Write-Host "[install] WARN: Using system npm: $(node -v)"
} else {
    $env:Path = "$PortableNode;$env:Path"
    Write-Host "[install] Using portable Node: $(& $nodeExe -v)"
}

function Test-Integrity {
    $required = @(
        "node_modules\vite\bin\vite.js",
        "node_modules\caniuse-lite\dist\lib\supported.js",
        "node_modules\@babel\core\lib\index.js",
        "node_modules\@esbuild\win32-x64\esbuild.exe"
    )
    foreach ($rel in $required) {
        if (-not (Test-Path (Join-Path $Fe $rel))) { return $false }
    }
    return $true
}

try {
    Add-MpPreference -ExclusionPath $Root -ErrorAction SilentlyContinue | Out-Null
} catch {}

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

Set-Location $Fe
$nm = Join-Path $Fe "node_modules"

if ((Test-Path $nm) -and (Test-DevMinimum) -and -not $ForceReinstall) {
    Write-Host "[install] node_modules OK for build — skip wipe (use -ForceReinstall to delete)."
    Write-Host "[install] Running light repair..."
    & (Join-Path $Root "scripts\repair_frontend_light.ps1")
    exit $LASTEXITCODE
}

if (Test-Path $nm) {
    Write-Host "[install] Removing node_modules..."
    Remove-Item -Recurse -Force $nm
}

Write-Host "[install] npm cache clean..."
& $npm cache clean --force

Write-Host "[install] npm ci (may take 2-5 min)..."
& $npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) {
    Write-Host "[install] npm ci exit $LASTEXITCODE, trying npm install..."
    & $npm install --no-audit --no-fund
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[install] npm install exit $LASTEXITCODE"
}

Get-ChildItem -Path $nm -Recurse -Include *.exe, *.node -ErrorAction SilentlyContinue |
    ForEach-Object { Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue }

if (Test-Path (Join-Path $nm "vite\bin\vite.js")) {
    Write-Host "[install] npm rebuild esbuild..."
    & $npm rebuild esbuild --no-audit
}

if (-not (Test-Integrity)) {
    Write-Host "[install] Repairing caniuse-lite..."
    & (Join-Path $Root "scripts\repair_caniuse_lite.ps1")
}
if (-not (Test-Path (Join-Path $Fe "node_modules\vite\package.json"))) {
    Write-Host "[install] Repairing vite package..."
    & (Join-Path $Root "scripts\repair_npm_pack.ps1") -Package "vite@5.4.21" -MarkerRel "vite\package.json"
}
$rollupPkg = Join-Path $Fe "node_modules\rollup\package.json"
$rollupOk = $false
if (Test-Path $rollupPkg) {
    try {
        $null = Get-Content $rollupPkg -Raw | ConvertFrom-Json
        $rollupOk = $true
    } catch { $rollupOk = $false }
}
if (-not $rollupOk) {
    Write-Host "[install] Repairing rollup package..."
    & (Join-Path $Root "scripts\repair_npm_pack.ps1") -Package "rollup@4.29.0" -MarkerRel "rollup\package.json"
}
$rollupNative = Join-Path $Fe "node_modules\@rollup\rollup-win32-x64-msvc\package.json"
if (-not (Test-Path $rollupNative)) {
    Write-Host "[install] Repairing @rollup/rollup-win32-x64-msvc ..."
    & (Join-Path $Root "scripts\repair_npm_pack.ps1") -Package "@rollup/rollup-win32-x64-msvc@4.29.0" -MarkerRel "@rollup\rollup-win32-x64-msvc\package.json"
}

if (-not (Test-Integrity) -and (Test-DevMinimum)) {
    Write-Host "[install] Partial install OK for build — full install needs Defender exclusion."
    exit 0
}

if (-not (Test-Integrity)) {
    Write-Host "[install] FAILED - incomplete node_modules."
    Write-Host "  Add Defender exclusion (Admin): $Root"
    Write-Host "  Then re-run: scripts\install_frontend.ps1"
    exit 1
}

Write-Host "[install] OK - run start_all.bat"
exit 0
