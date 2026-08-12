import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

describe("comparison select accessibility regression", () => {
  it("gives every A/B favorite and element selector a unique accessible name", () => {
    // Regression: QA-006 — four comparison comboboxes were anonymous to screen readers.
    // Found by /qa on 2026-08-12
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

    expect(source).toContain('aria-label="조성 A 즐겨찾기 불러오기"');
    expect(source).toContain('aria-label="조성 A 원소 추가"');
    expect(source).toContain('aria-label="조성 B 즐겨찾기 불러오기"');
    expect(source).toContain('aria-label="조성 B 원소 추가"');
  });
});
