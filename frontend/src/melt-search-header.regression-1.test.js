import { describe, expect, it } from "vitest";

import { meltSearchRightHint } from "./App.jsx";

// Regression: ISSUE-002 — collapsed melt-search header displayed only "선택".
// Found by /qa on 2026-07-22.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-22.md
describe("collapsed melt-search summary", () => {
  it("shows the target liquidus and candidate count", () => {
    const result = { candidates: Array.from({ length: 12 }, () => ({})) };

    expect(meltSearchRightHint(false, "200", result)).toBe("액상 200℃ · 후보 12개");
  });

  it("does not add redundant hint text while expanded", () => {
    expect(meltSearchRightHint(true, "200", { candidates: [{}] })).toBe("");
  });
});
