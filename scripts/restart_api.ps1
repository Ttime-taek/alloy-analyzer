# Stop whatever listens on :8000 and start this repo's api_server.py
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Get-PortOwnerPid([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function Test-ApiReady {
    try {
        $spec = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/openapi.json" -UseBasicParsing -TimeoutSec 4).Content | ConvertFrom-Json
        $paths = $spec.paths.PSObject.Properties.Name
        if ($paths -notcontains "/api/recommend_melt") { return $false }
        $about = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/about" -UseBasicParsing -TimeoutSec 4).Content | ConvertFrom-Json
        return ($about.api_features.recommend_melt -eq $true)
    } catch { return $false }
}

$pid8000 = Get-PortOwnerPid 8000
if ($pid8000) {
    Write-Host "[restart_api] Stopping PID $pid8000 on :8000"
    Stop-Process -Id $pid8000 -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

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
    Write-Host "[ERROR] Python not found."
    exit 1
}

Write-Host "[restart_api] Starting api_server.py..."
$proc = Start-Process -FilePath $py.Path -ArgumentList $py.Args -WorkingDirectory $Root -PassThru -WindowStyle Hidden
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$Root`"`r`ntitle Alloy API :8000`r`necho API PID $($proc.Id) — logs in the window that started this script.`r`npause" -WorkingDirectory $Root | Out-Null

for ($i = 0; $i -lt 40; $i++) {
    if ($proc.HasExited) {
        Write-Host "[ERROR] API exited (code $($proc.ExitCode))"
        exit 1
    }
    if (Test-ApiReady) {
        Write-Host "[restart_api] OK — http://127.0.0.1:8000/ (recommend_melt registered)"
        Write-Host "Refresh http://localhost:8000/"
        exit 0
    }
    Start-Sleep -Milliseconds 500
}
Write-Host "[ERROR] API did not become ready in 20s"
exit 1
