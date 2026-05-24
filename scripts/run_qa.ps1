# Quick QA: API smoke + UI gate (requires API on http://127.0.0.1:8000/)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
py -3 scripts/qa_http_smoke.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
py -3 scripts/qa_ui_selenium.py
exit $LASTEXITCODE
