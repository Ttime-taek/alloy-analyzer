# Repair common broken packages after npm install fails on Windows
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$repair = Join-Path $Root "scripts\repair_npm_pack.ps1"

& (Join-Path $Root "scripts\repair_caniuse_lite.ps1")

$packs = @(
    @{ P = "@babel/core@7.26.10"; M = "@babel\core\lib\index.js" },
    @{ P = "@vitejs/plugin-react@4.3.4"; M = "@vitejs\plugin-react\dist\index.js" },
    @{ P = "react@18.3.1"; M = "react\index.js" },
    @{ P = "react-dom@18.3.1"; M = "react-dom\index.js" }
)
foreach ($item in $packs) {
    & $repair -Package $item.P -MarkerRel $item.M
}

Write-Host "[repair] Done. Test: start_all.bat  or  cd frontend && npm run build"
