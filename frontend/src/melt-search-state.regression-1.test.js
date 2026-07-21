import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Regression: ISSUE-001 — old melt-search candidates remained above a new analysis result.
// Found by /qa on 2026-07-22.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-22.md
describe("melt-search result lifecycle", () => {
  it("clears prior melt-search output when a composition analysis starts", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");
    const handleAnalyze = source.match(
      /const handleAnalyze = async \(\) => \{([\s\S]*?)\n  \};\n\n  const handleReset/
    );

    expect(handleAnalyze?.[1]).toContain('setMeltRecError("")');
    expect(handleAnalyze?.[1]).toContain("setMeltRecResult(null)");
  });
});
