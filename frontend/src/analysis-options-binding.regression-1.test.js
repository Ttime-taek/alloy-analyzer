/**
 * Regression: pre-landing review found analysis results stayed visible when
 * report, literature, or wetting-temperature request options changed (2026-08-17).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { buildAnalysisInputSignature } from "./App.jsx";

describe("analysis request option binding", () => {
  const composition = { Sn: 96.5, Ag: 3, Cu: 0.5 };
  const options = { reportMode: "eng", literatureMode: "fast", wettingTempSelect: "auto" };

  it("invalidates results when any result-affecting option changes", () => {
    const original = buildAnalysisInputSignature("single", composition, {}, options);

    expect(buildAnalysisInputSignature("single", composition, {}, {
      ...options,
      reportMode: "lab"
    })).not.toBe(original);
    expect(buildAnalysisInputSignature("single", composition, {}, {
      ...options,
      literatureMode: "deep"
    })).not.toBe(original);
    expect(buildAnalysisInputSignature("single", composition, {}, {
      ...options,
      wettingTempSelect: "290"
    })).not.toBe(original);
  });

  it("sends a selected wetting temperature with the AI explanation request", () => {
    const source = readFileSync(fileURLToPath(new URL("./App.jsx", import.meta.url)), "utf8");

    expect(source).toContain('wettingTempSelect !== "auto"');
    expect(source).toContain('{ wetting_temp_c: Number(wettingTempSelect) }');
  });
});
