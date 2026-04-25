import { describe, it, expect } from "vitest";
import { BASELINE_ALLOY, buildSummaryStripModel } from "./summaryStrip";

describe("summaryStrip", () => {
  it("builds model from result.solidus using pinned baseline", () => {
    const m = buildSummaryStripModel({ solidus: 138.01 }, BASELINE_ALLOY);
    expect(m).not.toBeNull();
    expect(m.baseline.name).toBe("Sn1Ag25Bi0.7Cu");
    expect(m.baseline.solidusC).toBe(137.81);
    expect(m.solidusC).toBeCloseTo(138.01, 6);
  });

  it("returns null for missing/invalid solidus", () => {
    expect(buildSummaryStripModel(null)).toBeNull();
    expect(buildSummaryStripModel({})).toBeNull();
    expect(buildSummaryStripModel({ solidus: "x" })).toBeNull();
  });
});

