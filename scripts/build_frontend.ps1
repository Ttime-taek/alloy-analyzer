# Production UI build -> frontend/dist (portable Node 22, no npm-run PATH issues)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$NodeDir = Join-Path $Root "tools\node22"
$Node = Join-Path $NodeDir "node.exe"
$Fe = Join-Path $Root "frontend"
$Vite = Join-Path $Fe "node_modules\vite\bin\vite.js"
$Esbuild = Join-Path $Fe "node_modules\@esbuild\win32-x64\esbuild.exe"
$Log = Join-Path $Root "build-last.log"

if (-not (Test-Path $Node)) {
    Write-Host "[ERROR] Portable Node missing: $Node"
    Write-Host "Run: scripts\setup_portable_node.ps1"
    exit 1
}
if (-not (Test-Path $Vite)) {
    Write-Host "[ERROR] Vite missing. Run: scripts\fix_frontend_deps.cmd"
    exit 1
}
if (-not (Test-Path $Esbuild)) {
    Write-Host "[WARN] esbuild missing - repair_frontend_light.ps1 ..."
    & (Join-Path $Root "scripts\repair_frontend_light.ps1")
    if (-not (Test-Path $Esbuild)) {
        Write-Host "[ERROR] esbuild still missing. Run: scripts\fix_frontend_deps.cmd"
        exit 1
    }
}

$env:VITE_ESLINT_CHECK = "0"
if (Test-Path $NodeDir) { $env:Path = "$NodeDir;$env:Path" }

Push-Location $Fe
try {
    # npm run build uses `node` from PATH (portable Node first) — more reliable than
    # invoking vite.js with an absolute node path on some Windows setups.
    $Npm = Join-Path $NodeDir "npm.cmd"
    Write-Host "[build] npm run build (Node $(& $Node -v))"
    & $Npm run build 2>&1 | Tee-Object -FilePath $Log
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Vite build failed (exit $LASTEXITCODE). Log: $Log" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    if (-not (Test-Path (Join-Path $Fe "dist\index.html"))) {
        Write-Host "[ERROR] dist\index.html not created" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Built: frontend\dist" -ForegroundColor Green
    exit 0
}
finally {
    Pop-Location
}
