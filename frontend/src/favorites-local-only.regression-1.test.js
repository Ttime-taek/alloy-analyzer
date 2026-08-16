import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Regression: SECURITY-002 — the public browser proxied a shared favorites row through server credentials.
// Found by /cso on 2026-08-12.
// Report: .gstack/security-reports/2026-08-12-155000.json
describe("browser favorites storage boundary", () => {
  it("keeps browser favorites local and never calls the protected API", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");

    expect(source).toContain("const persistFavoritesLocal = (nextFavorites) =>");
    expect(source).toContain('window.localStorage.setItem("alloyFavorites"');
    expect(source).not.toContain('apiUrl("/api/favorites")');
    expect(source).not.toContain("syncFavoritesToServer");
  });
});
