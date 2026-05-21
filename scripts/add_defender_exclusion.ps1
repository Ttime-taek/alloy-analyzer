# Adds Windows Defender exclusion for this repo (requires Administrator).
$Root = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")).Path

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Write-Host "[ERROR] Administrator rights required."
    Write-Host ""
    Write-Host "Option A — double-click in Explorer:"
    Write-Host "  $Root\add_defender_exclusion_admin.bat"
    Write-Host "  (click Yes on the UAC prompt)"
    Write-Host ""
    Write-Host "Option B — manual (no Admin script):"
    Write-Host "  1) Windows Security (Windows 보안)"
    Write-Host "  2) Virus & threat protection -> Manage settings"
    Write-Host "  3) Exclusions -> Add an exclusion -> Folder"
    Write-Host "  4) Select: $Root"
    Write-Host ""
    Write-Host "Without exclusion you can still use: start_all.bat  ->  http://localhost:8000/"
    exit 1
}

try {
    $existing = @(Get-MpPreference -ErrorAction Stop).ExclusionPath | Where-Object { $_ -eq $Root }
    if ($existing) {
        Write-Host "[OK] Exclusion already present: $Root"
    } else {
        Add-MpPreference -ExclusionPath $Root -ErrorAction Stop
        Write-Host "[OK] Defender exclusion added: $Root"
    }
    Write-Host ""
    Write-Host "Next:"
    Write-Host "  scripts\fix_frontend_deps.cmd"
    Write-Host "  set ALLOY_DEV_VITE=1"
    Write-Host "  start_all.bat   (UI + API on http://localhost:8000/)"
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    Write-Host ""
    Write-Host "If your PC uses another antivirus, add the same folder there."
    exit 1
}
