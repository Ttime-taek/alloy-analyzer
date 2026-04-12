# Same PATH as a new CMD after Node install (fixes Explorer double-click)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
$user = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machine;$user"

$extras = @(
    "${env:ProgramFiles}\nodejs",
    "${env:ProgramFiles(x86)}\nodejs",
    "${env:LocalAppData}\Programs\nodejs"
)
foreach ($dir in $extras) {
    if (Test-Path (Join-Path $dir "node.exe")) {
        $env:Path = "$dir;$env:Path"
    }
}

# Python (탐색기 더블클릭 시 PATH가 비어 python/py를 못 찾는 경우)
$pyBase = "${env:LocalAppData}\Programs\Python"
if (Test-Path $pyBase) {
    $pyDir = Get-ChildItem -Path $pyBase -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if ($pyDir) {
        $pyexe = Join-Path $pyDir.FullName "python.exe"
        if (Test-Path $pyexe) {
            $env:Path = "$($pyDir.FullName);$($pyDir.FullName)\Scripts;$env:Path"
        }
    }
}
foreach ($name in @("Python313", "Python312", "Python311", "Python310")) {
    $pf = "${env:ProgramFiles}\$name"
    if (Test-Path (Join-Path $pf "python.exe")) {
        $env:Path = "$pf;$pf\Scripts;$env:Path"
        break
    }
}
$winApps = "${env:LocalAppData}\Microsoft\WindowsApps"
if (Test-Path (Join-Path $winApps "py.exe")) {
    $env:Path = "$winApps;$env:Path"
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] node.exe not found. Reinstall Node LTS from https://nodejs.org (check Add to PATH)."
    Write-Host "API only: run run_api_server.bat"
    exit 1
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] npm not found. Node.js 설치 중 'npm'도 포함되어야 합니다."
    Write-Host "새 CMD/PowerShell을 열고 다시 시도하세요."
    Write-Host "API only: run run_api_server.bat"
    exit 1
}

Set-Location (Join-Path $Root "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "[start_all] npm install..."
    npm install
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

npm run dev:all
exit $LASTEXITCODE
