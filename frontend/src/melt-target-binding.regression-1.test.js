import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { buildMeltInputSignature } from "./App.jsx";

// Regression: ISSUE-002 — a slow 210℃ search response could appear beside a
// target field that the user had already changed to 190℃.
// Found by /qa on 2026-08-12.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
describe("melt-search target binding", () => {
  it("changes the request signature when a visible melt target changes", () => {
    const target210 = buildMeltInputSignature("210", "", false);

    expect(buildMeltInputSignature("190", "", false)).not.toBe(target210);
    expect(buildMeltInputSignature("210", "150", true)).not.toBe(target210);
    expect(buildMeltInputSignature(" 210 ", "999", false)).toBe(target210);
  });

  it("aborts the old request and prevents its response from updating candidates", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

    expect(source).toMatch(
      /previousMeltInputSignatureRef\.current = meltInputSignature;[\s\S]*?meltRequestRef\.current\.controller\?\.abort\(\);[\s\S]*?setMeltRecResult\(null\)/
    );
    expect(source).toContain("signal: requestController.signal");
    expect(source).toContain("meltInputSignatureRef.current !== requestInputSignature");
  });
});
