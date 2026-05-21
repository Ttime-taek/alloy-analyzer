# Stack diagnostic — run: powershell -File scripts\diag_stack.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$Esbuild = Join-Path $Fe "node_modules\@esbuild\win32-x64\esbuild.exe"

Write-Host "========== Alloy stack diagnostic =========="
Write-Host "Root: $Root"
Write-Host ""

function Test-PortListen([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.OwningProcess }
    return $null
}

function Test-Http([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return "OK $($r.StatusCode) len=$($r.Content.Length)"
    } catch {
        return "FAIL $($_.Exception.Message)"
    }
}

Write-Host "--- Port 8000 ---"
$ownerPid = Test-PortListen 8000
if ($ownerPid) {
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    Write-Host "  LISTEN pid=$ownerPid name=$($proc.ProcessName)"
} else {
    Write-Host "  NOT listening"
}

Write-Host "`n--- HTTP ---"
@(
    "http://127.0.0.1:8000/openapi.json",
    "http://127.0.0.1:8000/api/about",
    "http://127.0.0.1:8000/",
    "http://localhost:8000/"
) | ForEach-Object { Write-Host "  $_ -> $(Test-Http $_)" }

Write-Host "`n--- frontend build deps ---"
@(
    "vite\dist\node\cli.js",
    "caniuse-lite\dist\lib\supported.js",
    "@esbuild\win32-x64\esbuild.exe",
    "@rollup\rollup-win32-x64-msvc\rollup.win32-x64-msvc.node"
) | ForEach-Object {
    $ok = Test-Path (Join-Path $Fe "node_modules\$_")
    Write-Host "  $_ : $(if($ok){'OK'}else{'MISSING'})"
}

Write-Host "`n--- esbuild ---"
if (Test-Path $Esbuild) {
    $ver = & cmd.exe /c "`"$Esbuild`" --version" 2>&1
    Write-Host "  version: $ver (exit $LASTEXITCODE)"
} else {
    Write-Host "  MISSING $Esbuild"
}

Write-Host "`n--- dist (UI served by API) ---"
$dist = Join-Path $Fe "dist\index.html"
Write-Host "  frontend\dist\index.html : $(if(Test-Path $dist){'OK'}else{'missing — run: cd frontend && npm run build'})"

Write-Host "`n--- API process (python api_server.py) ---"
Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "api_server" } |
    ForEach-Object { Write-Host "  pid=$($_.ProcessId) $($_.CommandLine)" }

Write-Host "`n--- Recommendations ---"
$listen8000 = Test-PortListen 8000
if ($listen8000) {
    Write-Host "  UI + API: http://localhost:8000/"
} else {
    Write-Host "  Run start_all.bat or run_api_server.bat in the repo root"
}
if (-not (Test-Path $dist)) {
    Write-Host "  Build UI: scripts\fix_frontend_deps.cmd  (or: cd frontend && npm run build)"
}
Write-Host "==========================================="
