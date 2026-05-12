#!/usr/bin/env bash
set -euo pipefail
NS="$(grep -m1 '^nameserver' /etc/resolv.conf | awk '{print $2}')"
if [[ -z "${NS:-}" ]]; then
  echo "ERROR: no nameserver in /etc/resolv.conf" >&2
  exit 1
fi
URL="http://${NS}:5173/"
B="${BROWSE_BIN:-/home/lg/.cursor/skills/gstack/browse/dist/browse}"
ROOT_WIN="/mnt/c/Coding/Auto/test7"
R="${ROOT_WIN}/.gstack/design-scratch"
mkdir -p "${R}/screenshots"
echo "URL=${URL}"
echo "BROWSE=${B}"
# 단일 chain으로 동일 브라우저 세션 유지(분리 호출 시 빈 탭에 스크린샷되는 경우 방지)
CHAIN_JSON="$(printf '%s' "[
  [\"goto\", \"${URL}\"],
  [\"wait\", \"--networkidle\"],
  [\"screenshot\", \"${R}/screenshots/first-impression.png\"],
  [\"snapshot\", \"-i\", \"-a\", \"-o\", \"${R}/screenshots/home-annotated.png\"],
  [\"responsive\", \"${R}/screenshots/home\"]
]")"
echo "${CHAIN_JSON}" | "${B}" chain
"${B}" console --errors || true
"${B}" perf || true
echo "Done. Listing ${R}/screenshots:"
ls -la "${R}/screenshots"
