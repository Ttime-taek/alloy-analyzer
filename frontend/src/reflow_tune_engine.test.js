import { describe, it, expect } from "vitest";
import {
  classifyPreset,
  recommendTuneForGoal,
  validateProfileTune,
  rulesVersion
} from "./reflow_tune_engine.js";

describe("reflow_tune_engine (shared JSON)", () => {
  it("exports rulesVersion", () => {
    expect(rulesVersion()).toBeGreaterThanOrEqual(1);
  });

  it("classifies 73 as mid-Bi not high-Bi", () => {
    const c = classifyPreset("73(Sn-3Ag-15Bi)");
    expect(c.isMidBi).toBe(true);
    expect(c.isHighBi).toBe(false);
  });

  it("recommend B+C for 78 preset matches Python snapshot", () => {
    const r = recommendTuneForGoal("B+C", "78(Sn-Bi)");
    expect(r.peakMargin).toBe(40);
    expect(r.overLiquidusTime).toBe(75);
    expect(r.coolRate).toBe(2.5);
  });

  it("validate flags TAL < 25 as error on mid-Bi profile", () => {
    const v = validateProfileTune(
      {
        rampRate: 1.5,
        preheatTime: 90,
        overLiquidusTime: 10,
        coolRate: 2,
        peakMargin: 35
      },
      "73(test)"
    );
    expect(v.errors.some((x) => x.includes("25"))).toBe(true);
  });

  it("validate mid-Bi nominal gets TAL band ok message", () => {
    const v = validateProfileTune(
      {
        rampRate: 1.5,
        preheatTime: 90,
        overLiquidusTime: 60,
        coolRate: 2.5,
        peakMargin: 35
      },
      "73(wide-paste)"
    );
    expect(v.errors.length).toBe(0);
    expect(v.oks.some((o) => o.includes("50~80"))).toBe(true);
  });
});
