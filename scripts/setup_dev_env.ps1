# Company-safe local dev environment setup.
# Keeps Python packages in .venv and npm cache under the repo to avoid user-profile/cache policy issues.
param(
    [switch]$SkipPython,
    [switch]$SkipFrontend,
    [switch]$ForceFrontendInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$RepoCache = Join-Path $Root ".cache"
$NpmCache = Join-Path $RepoCache "npm"

Write-Host "========== Alloy dev environment setup =========="
Write-Host "Root: $Root"

if (-not (Test-Path $RepoCache)) {
    New-Item -ItemType Directory -Path $RepoCache | Out-Null
}

if (-not $SkipPython) {
    Write-Host "`n--- Python (.venv) ---"
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating .venv..."
        py -3 -m venv $Venv
    } else {
        Write-Host ".venv exists"
    }

    Write-Host "Upgrading pip..."
    & $VenvPython -m pip install --upgrade pip

    Write-Host "Installing dev requirements..."
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-dev.txt")

    Write-Host "Verifying pytest..."
    & $VenvPython -c "import sys, pytest; print(sys.executable); print('pytest', pytest.__version__)"
}

if (-not $SkipFrontend) {
    Write-Host "`n--- Frontend (npm) ---"
    if (-not (Test-Path $Fe)) {
        throw "frontend directory not found: $Fe"
    }

    $env:NPM_CONFIG_CACHE = $NpmCache
    Write-Host "NPM cache: $env:NPM_CONFIG_CACHE"
    if (-not (Test-Path $NpmCache)) {
        New-Item -ItemType Directory -Path $NpmCache | Out-Null
    }

    Push-Location $Fe
    try {
        $hasLock = Test-Path "package-lock.json"
        $hasNodeModules = Test-Path "node_modules"
        if ($ForceFrontendInstall -or -not $hasNodeModules) {
            if ($hasLock) {
                Write-Host "Running npm ci..."
                npm ci --no-audit --no-fund
            } else {
                Write-Host "Running npm install..."
                npm install --no-audit --no-fund
            }
        } else {
            Write-Host "node_modules exists; running npm install to repair missing bins/packages..."
            npm install --no-audit --no-fund
        }

        Write-Host "Verifying frontend tools..."
        npm exec -- vite --version
        npm exec -- vitest --version
    } finally {
        Pop-Location
    }
}

Write-Host "`nDone."
Write-Host "Python tests: .\.venv\Scripts\python -m pytest tests -q"
Write-Host "Frontend tests: cd frontend; npm test -- --run"
Write-Host "==============================================="
