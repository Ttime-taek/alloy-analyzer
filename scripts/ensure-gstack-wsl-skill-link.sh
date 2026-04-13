#!/usr/bin/env bash
# Idempotent: ~/.cursor/skills/gstack -> Windows Cursor skills gstack (for browse $B / skills).
set -euo pipefail

if [[ ! -d /mnt/c ]]; then
  echo "This script is meant to run under WSL." >&2
  exit 1
fi

UP=""
if command -v powershell.exe >/dev/null 2>&1; then
  UP="$(powershell.exe -NoProfile -Command '[Console]::Out.Write($env:USERPROFILE)' 2>/dev/null | tr -d '\r')"
fi
if [[ -z "$UP" ]]; then
  echo "Could not read Windows USERPROFILE." >&2
  exit 1
fi

if ! command -v wslpath >/dev/null 2>&1; then
  echo "wslpath not found." >&2
  exit 1
fi

WIN_GSTACK="$(wslpath "$UP")/.cursor/skills/gstack"
if [[ ! -d "$WIN_GSTACK" ]]; then
  echo "gstack folder missing: $WIN_GSTACK" >&2
  echo "Copy or install gstack into %USERPROFILE%\\.cursor\\skills\\gstack first." >&2
  exit 1
fi

BROWSE="$WIN_GSTACK/browse/dist/browse"
if [[ ! -f "$BROWSE" ]]; then
  echo "browse binary missing: $BROWSE" >&2
  exit 1
fi

mkdir -p "$HOME/.cursor/skills"
ln -sfn "$WIN_GSTACK" "$HOME/.cursor/skills/gstack"

if [[ ! -x "$BROWSE" ]]; then
  echo "Warning: browse exists but is not executable: $BROWSE" >&2
  chmod +x "$BROWSE" 2>/dev/null || true
fi

echo "OK: $HOME/.cursor/skills/gstack -> $WIN_GSTACK"
test -x "$HOME/.cursor/skills/gstack/browse/dist/browse" && echo "browse: OK" || echo "browse: check chmod"
