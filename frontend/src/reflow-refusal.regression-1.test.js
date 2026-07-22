import { describe, expect, it } from "vitest";

import { buildReportSlides } from "./analysisChartReport.js";
import { shouldShowReflowProcessDetails } from "./App.jsx";

// Regression: ISSUE-005 — OOD results still displayed a peak recommendation and reflow chart.
// Found by /qa on 2026-07-22.
// Report: .gstack/qa-reports/qa-report-localhost-2026-07-22.md
describe("refused reflow recommendations", () => {
  it("hides interactive process details when policy refuses the result", () => {
    expect(shouldShowReflowProcessDetails({ processAllowed: false })).toBe(false);
    expect(shouldShowReflowProcessDetails({ processAllowed: true })).toBe(true);
  });

  it("replaces the report chart with explicit next actions", () => {
    const result = {
      solidus: 217.0,
      liquidus: 228.7,
      peak: 253.7,
      norm: { Sn: 98.9, Ag: 0.5, Cu: 0.5, Au: 0.1 },
      prediction_contract: { process_recommendation: { allowed: false } },
      alloy_inference: {
        solidus: 217.0,
        liquidus: 234.6,
        recommended_peak_c: 259.6,
        neighbors: []
      },
      props: {}
    };

    const slides = buildReportSlides({ result, profile: {}, melt: {} });
    const serialized = JSON.stringify(slides);

    expect(slides.some((slide) => slide.kind === "charts")).toBe(false);
    expect(slides.some((slide) => slide.id === "process-refused")).toBe(true);
    expect(serialized).not.toContain("권장 피크");
    expect(serialized).toContain("DSC");
  });
});
