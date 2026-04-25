import { describe, it, expect } from "vitest";

describe("App module", () => {
  it("default export is a function", async () => {
    const mod = await import("./App.jsx");
    expect(typeof mod.default).toBe("function");
  });
});
