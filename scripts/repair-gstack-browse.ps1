# Restore browse/dist/browse under %USERPROFILE%\.cursor\skills\gstack (WSL repair script).
$ErrorActionPreference = "Stop"
$sh = Join-Path $PSScriptRoot "repair-gstack-browse.sh"
if (-not (Test-Path $sh)) { Write-Error "Missing: $sh" }
$full = (Resolve-Path $sh).Path
if ($full -match '^([A-Za-z]):\\(.*)$') {
    $drive = $Matches[1].ToLower()
    $tail = $Matches[2].Replace('\', '/')
    $wslPath = "/mnt/$drive/$tail"
} else {
    Write-Error "Could not map to WSL path: $full"
}
wsl -e bash -l "$wslPath"
