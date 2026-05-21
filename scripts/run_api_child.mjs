/**
 * npm `api` 스크립트: test7 루트에서 api_server.py 실행 (Windows/macOS/Linux 공통).
 * shell 인용 문제를 피하기 위해 spawn 사용.
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const pf = process.env.ProgramFiles || "C:\\Program Files";
const py312 = path.join(pf, "Python312", "python.exe");
const py313 = path.join(pf, "Python313", "python.exe");
const py311 = path.join(pf, "Python311", "python.exe");
const chain =
  process.platform === "win32"
    ? [
        ...(fs.existsSync(py312) ? [[py312, ["api_server.py"]]] : []),
        ...(fs.existsSync(py313) ? [[py313, ["api_server.py"]]] : []),
        ...(fs.existsSync(py311) ? [[py311, ["api_server.py"]]] : []),
        ["py", ["-3", "api_server.py"]],
        ["python", ["api_server.py"]],
      ]
    : [
        ["python3", ["api_server.py"]],
        ["python", ["api_server.py"]],
      ];

let i = 0;

function runNext() {
  if (i >= chain.length) {
    console.error("[api] python / py / python3 를 찾을 수 없습니다.");
    process.exit(1);
  }
  const [cmd, args] = chain[i++];
  const child = spawn(cmd, args, {
    cwd: root,
    stdio: ["ignore", "pipe", "pipe"],
    shell: process.platform === "win32" && !String(cmd).includes(path.sep),
    env: {
      ...process.env,
      // 명시: 부모 셸에 ALLOY_API_HOST가 없으면 모든 인터페이스에 바인딩(외부 접속)
      ...(process.env.ALLOY_API_HOST ? {} : { ALLOY_API_HOST: "0.0.0.0" }),
    },
  });
  child.stdout?.pipe(process.stdout);
  child.stderr?.pipe(process.stderr);
  child.on("error", () => runNext());
  child.on("exit", (code, signal) => {
    if (signal) process.exit(1);
    process.exit(code ?? 0);
  });
}

runNext();
