import { describe, expect, it } from "vitest";

import { roundedDisplayDelta } from "./App.jsx";

describe("comparison delta presentation regression", () => {
  it("normalizes sub-precision negative differences to positive zero", () => {
    // Regression: QA-005 — equal displayed Fmax values produced a -0.00 mN delta.
    // Found by /qa on 2026-08-12
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    const delta = roundedDisplayDelta(1.804, 1.8001);

    expect(delta).toBe(0);
    expect(Object.is(delta, -0)).toBe(false);
  });

  it("keeps differences that are visible at two decimal places", () => {
    expect(roundedDisplayDelta(1.806, 1.8)).toBe(-0.01);
    expect(roundedDisplayDelta(1.8, 1.806)).toBe(0.01);
  });
});
