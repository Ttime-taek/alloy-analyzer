import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { analysisModeForKey } from "./App.jsx";

// Regression: ISSUE-005 — analysis tabs ignored the ARIA Left/Right Arrow interaction.
// Found by /qa on 2026-08-12.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
describe("analysis tab keyboard navigation", () => {
  it("moves between both tabs and supports Home/End", () => {
    expect(analysisModeForKey("single", "ArrowRight")).toBe("compare");
    expect(analysisModeForKey("compare", "ArrowLeft")).toBe("single");
    expect(analysisModeForKey("compare", "Home")).toBe("single");
    expect(analysisModeForKey("single", "End")).toBe("compare");
    expect(analysisModeForKey("single", "Enter")).toBeNull();
  });

  it("uses roving tabindex and focuses the activated tab", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

    expect(source).toContain("tabIndex={active ? 0 : -1}");
    expect(source).toContain("nextTab?.focus()");
    expect(source).toContain("handleModeTabKeyDown(event, \"single\")");
    expect(source).toContain("handleModeTabKeyDown(event, \"compare\")");
  });
});
