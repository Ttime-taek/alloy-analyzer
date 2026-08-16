import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { compositionAnalyzeBlockReason } from "./App.jsx";

// Regression: ISSUE-004 — balanced negative wt% values appeared valid and reached the API.
// Found by /qa on 2026-08-12.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
describe("composition non-negative validation", () => {
  it("blocks a negative element even when the composition totals 100%", () => {
    expect(
      compositionAnalyzeBlockReason({ Sn: 98, Ag: -1, Cu: 1, Bi: 1, In: 1 }, "조성 A")
    ).toBe("조성 A의 Ag 값은 0 이상이어야 합니다.");
  });

  it("keeps the native minimum constraint on both composition input paths", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");
    const matches = source.match(/type="number"\n\s+step="0\.01"\n\s+min="0"/g) || [];

    expect(matches).toHaveLength(2);
  });
});
