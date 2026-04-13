# Run once: WSL ~/.cursor/skills/gstack -> %USERPROFILE%\.cursor\skills\gstack (gstack browse for skills).
$ErrorActionPreference = "Stop"
$sh = Join-Path $PSScriptRoot "ensure-gstack-wsl-skill-link.sh"
if (-not (Test-Path $sh)) {
    Write-Error "Missing: $sh"
}
if (-not (Test-Path "$env:USERPROFILE\.cursor\skills\gstack")) {
    Write-Error "Missing: $env:USERPROFILE\.cursor\skills\gstack — copy gstack there first (see project docs / gstack install)."
}
$full = (Resolve-Path $sh).Path
if ($full -match '^([A-Za-z]):\\(.*)$') {
    $drive = $Matches[1].ToLower()
    $tail = $Matches[2].Replace('\', '/')
    $wslPath = "/mnt/$drive/$tail"
} else {
    Write-Error "Could not map to WSL path: $full"
}
wsl -e bash -l "$wslPath"
