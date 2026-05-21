# Extract an npm package with tar when npm install drops files (Windows Defender)
param(
    [Parameter(Mandatory = $true)][string]$Package,
    [Parameter(Mandatory = $true)][string]$MarkerRel
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Fe = Join-Path $Root "frontend"
$npm = Join-Path $Root "tools\node22\npm.cmd"
if (-not (Test-Path $npm)) { $npm = Join-Path $env:ProgramFiles "nodejs\npm.cmd" }
$marker = Join-Path $Fe "node_modules\$MarkerRel"
if (Test-Path $marker) { return }

$pkgDir = $Package -replace "/", "\"
$dest = Join-Path $Fe "node_modules\$pkgDir"
Write-Host "[repair] npm pack $Package ..."
Set-Location $Fe
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$packOut = (& $npm pack $Package --pack-destination $env:TEMP 2>&1 | Out-String)
$ErrorActionPreference = $prevEap
$tgz = $null
if ($packOut -match 'filename:\s*(\S+\.tgz)') {
    $tgz = Join-Path $env:TEMP $Matches[1].Trim()
} elseif ($packOut -match '([\w\.\-]+\.tgz)\s*$') {
    $tgz = Join-Path $env:TEMP $Matches[1].Trim()
}
if (-not $tgz -or -not (Test-Path $tgz)) {
    $found = Get-ChildItem $env:TEMP -Filter "*.tgz" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($found) { $tgz = $found.FullName }
}
if (-not (Test-Path $tgz)) { throw "pack failed: $Package" }
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
New-Item -ItemType Directory -Force -Path $dest | Out-Null
tar -xzf $tgz -C $dest --strip-components=1
if (-not (Test-Path $marker)) { throw "repair failed: $Package -> $MarkerRel" }
Write-Host "[repair] OK $Package"
