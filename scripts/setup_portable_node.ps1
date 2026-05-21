# Download Node 22 LTS portable for this repo (avoids broken system Node 24 + npm on Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Tools = Join-Path $Root "tools\node22"
$Zip = Join-Path $env:TEMP "node-v22-win-x64.zip"
$Url = "https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip"

if (Test-Path (Join-Path $Tools "node.exe")) {
    Write-Host "[node22] Already present: $Tools"
    & (Join-Path $Tools "node.exe") -v
    exit 0
}

Write-Host "[node22] Downloading Node 22.14.0 ..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing

Write-Host "[node22] Extracting to $Tools ..."
if (Test-Path $Tools) { Remove-Item -Recurse -Force $Tools }
New-Item -ItemType Directory -Path (Split-Path $Tools) -Force | Out-Null
Expand-Archive -Path $Zip -DestinationPath (Split-Path $Tools) -Force
$inner = Get-ChildItem (Split-Path $Tools) -Directory | Where-Object { $_.Name -like "node-v22*" } | Select-Object -First 1
if (-not $inner) { throw "Extract failed" }
Move-Item -Path $inner.FullName -Destination $Tools -Force
Remove-Item $Zip -Force -ErrorAction SilentlyContinue

Write-Host "[node22] OK: $(& (Join-Path $Tools 'node.exe') -v)"
