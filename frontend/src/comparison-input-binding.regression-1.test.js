import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { buildAnalysisInputSignature } from "./App.jsx";

// Regression: ISSUE-001 — comparison metrics stayed mounted and were relabelled
// with edited A/B inputs that had never produced those metrics.
// Found by /qa on 2026-08-12.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
describe("comparison result input binding", () => {
  it("changes the request signature when either comparison composition changes", () => {
    const original = buildAnalysisInputSignature(
      "compare",
      { Sn: 96.5, Ag: 3, Cu: 0.5 },
      { Sn: 99, Cu: 1 }
    );

    expect(buildAnalysisInputSignature(
      "compare",
      { Sn: 96.4, Ag: 3.1, Cu: 0.5 },
      { Sn: 99, Cu: 1 }
    )).not.toBe(original);
    expect(buildAnalysisInputSignature(
      "compare",
      { Sn: 96.5, Ag: 3, Cu: 0.5 },
      { Sn: 98.9, Cu: 1.1 }
    )).not.toBe(original);
  });

  it("clears comparison output and rejects a late response for an old signature", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

    expect(source).toMatch(
      /previousAnalysisInputSignatureRef\.current = analysisInputSignature;[\s\S]*?setCompareResult\(null\)/
    );
    expect(source).toContain("analysisInputSignatureRef.current !== requestInputSignature");
  });
});
