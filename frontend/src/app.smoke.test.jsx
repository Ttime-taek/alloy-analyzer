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
});
