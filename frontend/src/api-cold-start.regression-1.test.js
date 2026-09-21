import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Regression: 2026-09-21 web audit — Render cold start showed a developer-only
// "8000 포트 · api_server.py 재실행" warning to end users and never retried.
describe("API cold start handling", () => {
  const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

  it("retries the capability probe while the server is waking", () => {
    expect(source).toMatch(/RETRY_DELAYS_MS/);
    expect(source).toMatch(/setMeltSupport\("waking"\)/);
    expect(source).toMatch(/setMeltSupport\("unreachable"\)/);
  });

  it("shows developer port hints only in dev builds", () => {
    const idx = source.lastIndexOf("8000 포트");
    expect(idx).toBeGreaterThan(-1);
    const before = source.slice(Math.max(0, idx - 400), idx);
    expect(before).toMatch(/import\.meta\.env\.DEV/);
  });
});

describe("production copy", () => {
  it("keeps the API(8000) restart hint behind the dev flag", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");
    const idx = source.indexOf("API(8000)를 재시작");
    expect(idx).toBeGreaterThan(-1);
    expect(source.slice(Math.max(0, idx - 120), idx)).toMatch(/import\.meta\.env\.DEV/);
  });
});
