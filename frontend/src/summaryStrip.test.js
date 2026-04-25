import { describe, it, expect } from "vitest";
import { BASELINE_ALLOY, buildSummaryStripModel, formatSignedTempDeltaC } from "./summaryStrip";

describe("summaryStrip", () => {
  it("formats signed deltas with 0.1°C rounding", () => {
    expect(formatSignedTempDeltaC(0)).toBe("0.0℃");
    expect(formatSignedTempDeltaC(0.01)).toBe("+0.0℃");
    expect(formatSignedTempDeltaC(0.04)).toBe("+0.0℃");
    expect(formatSignedTempDeltaC(0.05)).toBe("+0.1℃");
    expect(formatSignedTempDeltaC(-0.05)).toBe("-0.1℃");
    expect(formatSignedTempDeltaC(1.26)).toBe("+1.3℃");
    expect(formatSignedTempDeltaC(-1.24)).toBe("-1.2℃");
  });

  it("builds model from result.solidus using pinned baseline", () => {
    const m = buildSummaryStripModel({ solidus: 138.01 }, BASELINE_ALLOY);
    expect(m).not.toBeNull();
    expect(m.baseline.name).toBe("Sn1Ag25Bi0.7Cu");
    expect(m.baseline.solidusC).toBe(137.81);
    expect(m.solidusC).toBeCloseTo(138.01, 6);
    expect(m.deltaSolidusText).toBe("+0.2℃");
  });

  it("returns null for missing/invalid solidus", () => {
    expect(buildSummaryStripModel(null)).toBeNull();
    expect(buildSummaryStripModel({})).toBeNull();
    expect(buildSummaryStripModel({ solidus: "x" })).toBeNull();
  });
});

