import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { compositionInputAccessibleName, compositionInputId } from "./App.jsx";

// Regression: ISSUE-002 — composition percentage inputs had no accessible names.
// Found by /qa on 2026-07-15.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-15-2.md
describe("composition input accessibility", () => {
  it("gives matching A and B elements distinct IDs and names", () => {
    expect(compositionInputId("Sn", "A")).toBe("composition-a-sn");
    expect(compositionInputId("Sn", "B")).toBe("composition-b-sn");
    expect(compositionInputAccessibleName("Sn", "A")).toBe("조성 A Sn wt%");
    expect(compositionInputAccessibleName("Sn", "B")).toBe("조성 B Sn wt%");
  });

  it("wires the accessible naming helper into both composition input paths", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

    expect(source).toContain("<label htmlFor={inputId}>{el}</label>");
    expect(source).toContain("aria-label={compositionInputAccessibleName(el, side)}");
    expect(source).toContain('htmlFor={compositionInputId(el, "A")}');
    expect(source).toContain('aria-label={compositionInputAccessibleName(el, "A")}');
  });
});
