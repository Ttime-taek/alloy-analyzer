import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Regression: DX-002 — initial render requested /api/about twice.
// Found by /devex-review on 2026-08-12.
// Report: .gstack/devex-reports/2026-08-12-devex-review.md
describe("about bootstrap", () => {
  it("uses the combined capability bootstrap as the only about request", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");
    const aboutRequests = source.match(/fetch\(apiUrl\(`?\/api\/about/g) || [];

    expect(aboutRequests).toHaveLength(1);
  });
});
