#!/usr/bin/env bash
# Restore browse/dist/browse (+ find-browse) into %USERPROFILE%\.cursor\skills\gstack:
# 1) copy from a WSL gstack clone that already has a built binary
# 2) else run bun install && bun run build in that clone, then copy
set -euo pipefail

if [[ ! -d /mnt/c ]]; then
  echo "Run this script under WSL." >&2
  exit 1
fi

if ! command -v powershell.exe >/dev/null 2>&1 || ! command -v wslpath >/dev/null 2>&1; then
  echo "Need powershell.exe and wslpath (WSL)." >&2
  exit 1
fi

UP="$(powershell.exe -NoProfile -Command '[Console]::Out.Write($env:USERPROFILE)' 2>/dev/null | tr -d '\r')"
if [[ -z "$UP" ]]; then
  echo "Could not read Windows USERPROFILE." >&2
  exit 1
fi

WIN_GSTACK="$(wslpath "$UP")/.cursor/skills/gstack"
DIST="$WIN_GSTACK/browse/dist"
BROWSE_BIN="$DIST/browse"

gstack_roots=()
if [[ -n "${GSTACK_ROOT:-}" && -d "$GSTACK_ROOT" ]]; then
  gstack_roots+=("$GSTACK_ROOT")
fi
for d in "$HOME/gstack" "/home/$USER/gstack"; do
  [[ -d "$d" ]] || continue
  gstack_roots+=("$d")
done

sync_dist_from() {
  local src_root="$1"
  local src_dist="$src_root/browse/dist"
  if [[ ! -d "$src_dist" ]]; then
    return 1
  fi
  if [[ -f "$src_dist/browse" ]] && [[ -x "$src_dist/browse" ]]; then
    mkdir -p "$DIST"
    cp -a "$src_dist/browse" "$src_dist/find-browse" "$DIST/" 2>/dev/null || cp -a "$src_dist/browse" "$DIST/"
    [[ -f "$src_dist/find-browse" ]] && cp -a "$src_dist/find-browse" "$DIST/" 2>/dev/null || true
    [[ -f "$src_dist/.version" ]] && cp -a "$src_dist/.version" "$DIST/" || true
    chmod +x "$DIST/browse" 2>/dev/null || true
    [[ -f "$DIST/find-browse" ]] && chmod +x "$DIST/find-browse" 2>/dev/null || true
    return 0
  fi
  return 1
}

build_in_repo() {
  local root="$1"
  if [[ ! -f "$root/package.json" ]]; then
    return 1
  fi
  if ! command -v bun >/dev/null 2>&1; then
    echo "bun is required. Install: https://bun.sh — or run gstack ./setup from $root" >&2
    return 1
  fi
  echo "Building browse (bun install && bun run build) in: $root"
  ( cd "$root" && bun install && bun run build )
}

# Repair if missing, not executable, or implausibly small (corrupt / only-.version tree)
if [[ -f "$BROWSE_BIN" ]] && [[ -x "$BROWSE_BIN" ]]; then
  sz="$(stat -c%s "$BROWSE_BIN" 2>/dev/null || echo 0)"
  if [[ "${sz:-0}" -ge 1000000 ]]; then
    echo "browse already OK: $BROWSE_BIN"
    exit 0
  fi
fi

mkdir -p "$WIN_GSTACK/browse"

for root in "${gstack_roots[@]}"; do
  if sync_dist_from "$root"; then
    if [[ -x "$BROWSE_BIN" ]]; then
      echo "OK: copied browse from $root/browse/dist -> $DIST"
      exit 0
    fi
  fi
done

for root in "${gstack_roots[@]}"; do
  if [[ -f "$root/package.json" ]] && [[ -f "$root/setup" ]]; then
    if build_in_repo "$root"; then
      if sync_dist_from "$root" && [[ -x "$BROWSE_BIN" ]]; then
        echo "OK: built and copied browse from $root -> $DIST"
        exit 0
      fi
    fi
  fi
done

echo "Could not repair browse under: $DIST" >&2
echo "Fix manually:" >&2
echo "  1) Clone gstack, then: cd gstack && ./setup   (needs bun)" >&2
echo "  2) Or copy browse/dist/browse from a machine that has it into:" >&2
echo "     $DIST" >&2
exit 1
