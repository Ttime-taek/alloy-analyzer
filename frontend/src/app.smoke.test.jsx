import fs from "node:fs";
import path from "node:path";

import { describe, it, expect } from "vitest";

describe("App module", () => {
  it("default export is a function", async () => {
    const mod = await import("./App.jsx");
    expect(typeof mod.default).toBe("function");
  });

  it("includes P in the solder element picker list", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "./App.jsx"), "utf8");
    const match = source.match(/const solderElems = \[([\s\S]*?)\];/);
    expect(match?.[1]).toContain('"P"');
  });

  it("formats the primary tensile KPI from the analysis result", async () => {
    const { formatTensilePrimary, tensileSummaryLabel } = await import("./App.jsx");
    const props = {
      tensile_strength: 48.5,
      tensile_strength_db_mpa: 48.5,
      tensile_strength_basis: "db_priority"
    };

    expect(formatTensilePrimary(props)).toBe("48.5 MPa");
    expect(tensileSummaryLabel(props)).toBe("인장 (DB우선)");
    expect(formatTensilePrimary({})).toBe("—");
  });
});
