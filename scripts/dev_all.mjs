/**
 * Vite + FastAPI 동시 실행 (concurrently 없음 — Windows에서 .bin PATH 문제 회피)
 * frontend 폴더에서: node ../scripts/dev_all.mjs
 */
import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontend = path.join(root, "frontend");
const apiScript = path.join(root, "scripts", "run_api_child.mjs");
const isWin = process.platform === "win32";
const npmCmd = isWin ? "npm.cmd" : "npm";

function killPort8000OnWin() {
  if (!isWin) return;
  // 8000 포트 충돌 시(이전 api_server가 남아있을 때) 자동 정리
  const cmd = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }",
  ];
  spawnSync("powershell.exe", cmd, { stdio: "ignore" });
}

killPort8000OnWin();

const api = spawn(process.execPath, [apiScript], {
  cwd: frontend,
  stdio: "inherit",
  env: process.env,
});

let web = null;
let finished = false;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function isApiUp() {
  return new Promise((resolve) => {
    const req = http.get(
      {
        // Windows에서 localhost→IPv6(::1)만 시도해 127.0.0.1:8000이 열려도 실패할 수 있음
        hostname: "127.0.0.1",
        port: 8000,
        family: 4,
        path: "/openapi.json",
        timeout: 2000,
      },
      (res) => {
        res.resume();
        resolve(true);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

function killOthers(exited) {
  if (api && api !== exited) {
    try {
      api.kill(isWin ? undefined : "SIGTERM");
    } catch (_) {}
  }
  if (web && web !== exited) {
    try {
      web.kill(isWin ? undefined : "SIGTERM");
    } catch (_) {}
  }
}

function finish(code) {
  if (finished) return;
  finished = true;
  killOthers(null);
  process.exit(code ?? 0);
}

process.on("SIGINT", () => finish(0));
process.on("SIGTERM", () => finish(0));

api.on("exit", (code, signal) => {
  // API가 죽으면, 웹도 같이 종료(프록시 ECONNREFUSED 방지 목적)
  if (!finished) finish(signal ? 1 : code);
});

// 1) API 먼저 띄우고 ready 될 때까지 기다린 뒤 2) Vite를 시작
let ready = false;
for (let attempt = 0; attempt < 40; attempt++) {
  // 최대 20초 대기
  // eslint-disable-next-line no-await-in-loop
  ready = await isApiUp();
  if (ready) break;
  // eslint-disable-next-line no-await-in-loop
  await sleep(500);
}

if (!ready) {
  console.error("[dev_all] API가 20초 내에 준비되지 않았습니다. (localhost:8000/openapi.json 연결 실패)");
  finish(1);
}

// Windows에서 npm.cmd 직접 spawn이 환경에 따라 EINVAL이 날 수 있어
// cmd.exe 경유로 실행합니다.
if (isWin) {
  const comspec = process.env.ComSpec || "cmd.exe";
  web = spawn(comspec, ["/c", `${npmCmd} run dev`], {
    cwd: frontend,
    stdio: "inherit",
    env: process.env,
  });
} else {
  web = spawn(npmCmd, ["run", "dev"], {
    cwd: frontend,
    stdio: "inherit",
    env: process.env,
  });
}

web.on("exit", (code, signal) => {
  if (!finished) finish(signal ? 1 : code);
});
