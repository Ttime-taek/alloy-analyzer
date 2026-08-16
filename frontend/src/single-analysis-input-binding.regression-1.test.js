import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { buildAnalysisInputSignature } from "./App.jsx";

// Regression: ISSUE-003 — single-analysis KPIs and the AI explanation action
// remained visible after the user edited the composition.
// Found by /qa on 2026-08-12.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
describe("single-analysis result input binding", () => {
  it("uses a canonical signature and detects a composition edit", () => {
    const original = buildAnalysisInputSignature("single", { Sn: 96.5, Ag: 3, Cu: 0.5 });

    expect(buildAnalysisInputSignature("single", { Cu: 0.5, Sn: 96.5, Ag: 3 })).toBe(original);
    expect(buildAnalysisInputSignature("single", { Sn: 96.4, Ag: 3.1, Cu: 0.5 })).not.toBe(original);
  });

  it("clears the result and its dependent AI/report state before paint", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");
    const invalidation = source.match(
      /useLayoutEffect\(\(\) => \{\n[ ]{4}if \(previousAnalysisInputSignatureRef[\s\S]*?\n[ ]{2}\}, \[analysisInputSignature\]\);/
    );

    expect(invalidation?.[0]).toContain("setResult(null)");
    expect(invalidation?.[0]).toContain("explanationRequestRef.current?.abort()");
    expect(invalidation?.[0]).toContain("setAiExplanationLoading(false)");
    expect(invalidation?.[0]).toContain("setChartReportOpen(false)");
  });
});
