# Alloy Predictor — API + built UI on http://localhost:8000/ (stable on Windows)
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$Dist = Join-Path $Fe "dist\index.html"
$NodeDir = Join-Path $Root "tools\node22"
$Npm = Join-Path $NodeDir "npm.cmd"
$script:ApiStartedHere = $false
$script:ApiProc = $null

if (Test-Path $NodeDir) { $env:Path = "$NodeDir;$env:Path" }

function Wait-Key([string]$Msg) {
    Write-Host ""
    Write-Host $Msg -ForegroundColor Yellow
    Read-Host "Press Enter to close"
}

function Test-Port([int]$P) {
    [bool](Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Stop-Port([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) { return }
    Write-Host "[start_all] Stop :$Port PID $($c.OwningProcess)"
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

function Test-EsbuildReady {
    Test-Path (Join-Path $Fe "node_modules\@esbuild\win32-x64\esbuild.exe")
}

function Test-FrontendBuildStale {
    if (-not (Test-Path $Dist)) { return $true }
    $distTime = (Get-Item $Dist).LastWriteTimeUtc
    $candidates = @(
        (Join-Path $Fe "vite.config.mjs"),
        (Join-Path $Fe "package.json")
    )
    if (Test-Path (Join-Path $Fe "src")) {
        $candidates += Get-ChildItem (Join-Path $Fe "src") -Recurse -File -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
    }
    foreach ($path in $candidates) {
        if (-not (Test-Path $path)) { continue }
        if ((Get-Item $path).LastWriteTimeUtc -gt $distTime) { return $true }
    }
    return $false
}

function Ensure-FrontendBuild {
    if ((Test-Path $Dist) -and -not (Test-FrontendBuildStale)) { return $true }
    if (-not (Test-Path $Npm)) {
        Write-Host "[ERROR] Missing $Npm"
        return $false
    }
    if (Test-Path $Dist) {
        Write-Host "[start_all] Frontend source changed — rebuilding UI..."
    } else {
        Write-Host "[start_all] Building UI (npm run build)..."
    }
    $env:VITE_ESLINT_CHECK = "0"
    if (Test-Path $NodeDir) { $env:Path = "$NodeDir;$env:Path" }
    Push-Location $Fe
    & $Npm run build 2>&1 | ForEach-Object { Write-Host $_ }
    $ok = (Test-Path $Dist)
    Pop-Location
    return $ok
}

function Test-ApiReady {
    try {
        $spec = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/openapi.json" -UseBasicParsing -TimeoutSec 4).Content | ConvertFrom-Json
        if ($spec.paths.PSObject.Properties.Name -notcontains "/api/recommend_melt") { return $false }
        $about = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/about" -UseBasicParsing -TimeoutSec 4).Content | ConvertFrom-Json
        return ($about.api_features.recommend_melt -eq $true)
    } catch { return $false }
}

function Test-UiReady {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -eq 200 -and $r.Content.Length -gt 100)
    } catch { return $false }
}

function Stop-Api {
    if ($script:ApiStartedHere -and $script:ApiProc -and -not $script:ApiProc.HasExited) {
        Write-Host "[start_all] Stopping API (PID $($script:ApiProc.Id))..."
        Stop-Process -Id $script:ApiProc.Id -Force -ErrorAction SilentlyContinue
    }
}

function Start-Api {
    if (Test-ApiReady) {
        Write-Host "[start_all] API already on :8000"
        return $true
    }
    if (Test-Port 8000) {
        Write-Host "[start_all] Restarting stale process on :8000..."
        Stop-Port 8000
    }
    Write-Host "[start_all] Starting API on :8000..."
    $py = $null
    foreach ($c in @(
            @{ E = $env:ALLOY_PYTHON; A = @("api_server.py") },
            @{ E = "py"; A = @("-3", "api_server.py") },
            @{ E = "python"; A = @("api_server.py") }
        )) {
        if ($c.E -and (Get-Command $c.E -ErrorAction SilentlyContinue)) {
            $py = @{ Path = $c.E; Args = $c.A }
            break
        }
    }
    if (-not $py) {
        Write-Host "[ERROR] Python not found (py -3 or python)."
        return $false
    }
    $script:ApiProc = Start-Process -FilePath $py.Path -ArgumentList $py.Args -WorkingDirectory $Root -PassThru -WindowStyle Hidden
    $script:ApiStartedHere = $true
    for ($i = 0; $i -lt 40; $i++) {
        if (Test-ApiReady) { return $true }
        if ($script:ApiProc.HasExited) {
            Write-Host "[ERROR] API exited (code $($script:ApiProc.ExitCode))"
            return $false
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "[ERROR] API not ready in 20s"
    return $false
}

Write-Host ""
Write-Host "=========================================="
Write-Host "  Alloy Predictor - start_all"
Write-Host "=========================================="
Write-Host "  Open: http://localhost:8000/"
Write-Host "  (UI + API on one server)"
Write-Host ""
Write-Host "  Close this window or Ctrl+C = stop API"
Write-Host "=========================================="
Write-Host ""

if (-not (Test-EsbuildReady)) {
    Write-Host "[start_all] Repairing frontend..."
    $repair = Join-Path $Root "scripts\repair_frontend_light.ps1"
    if (Test-Path $repair) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $repair | ForEach-Object { Write-Host $_ }
    }
}
if (-not (Ensure-FrontendBuild)) {
    Wait-Key "[ERROR] Run scripts\fix_frontend_deps.cmd then retry"
    exit 1
}

try {
    if (-not (Start-Api)) {
        Wait-Key "[ERROR] Could not start API on :8000"
        exit 1
    }
    Write-Host "[start_all] API ready on :8000"

    if (Test-UiReady) {
        Write-Host "[start_all] UI ready at http://localhost:8000/"
    } else {
        Write-Host "[WARN] UI static files may be missing — rebuild with scripts\fix_frontend_deps.cmd"
    }

    if ($env:ALLOY_OPEN_BROWSER -ne "0") {
        Start-Process "http://localhost:8000/"
    }

    Write-Host ""
    Write-Host "Running. Use http://localhost:8000/"
    Write-Host "If the browser shows 'Failed to fetch', refresh after this message appears."
    Write-Host "Press Ctrl+C to stop."
    Write-Host ""

    while ($true) {
        if ($script:ApiStartedHere -and $script:ApiProc.HasExited) {
            Write-Host "[ERROR] API stopped (code $($script:ApiProc.ExitCode))"
            break
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host ""
    Write-Host "[start_all] Shutting down..."
    Stop-Api
}

Wait-Key "Press Enter to close"
exit 0
