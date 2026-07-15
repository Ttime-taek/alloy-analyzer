import { afterEach, describe, expect, it, vi } from "vitest";

// Regression: mobile production builds without VITE_API_BASE_URL tried the browser origin
// and displayed localhost (127.0.0.1:8000) recovery instructions.
// Found from the user-provided mobile screenshot on 2026-07-16.
describe("production API origin fallback", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("uses Render on the Alloy Analyzer Vercel production domain", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.stubGlobal("window", { location: { hostname: "alloy-analyzer.vercel.app" } });
    vi.resetModules();

    const { apiUrl, hasConfiguredApiBaseUrl } = await import("./api.js");

    expect(apiUrl("/api/about")).toBe("https://alloy-analyzer.onrender.com/api/about");
    expect(hasConfiguredApiBaseUrl).toBe(true);
  });

  it("also protects Alloy Analyzer Vercel preview deployments", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.stubGlobal("window", {
      location: { hostname: "alloy-analyzer-git-fix-example.vercel.app" }
    });
    vi.resetModules();

    const { apiUrl } = await import("./api.js");

    expect(apiUrl("api/favorites")).toBe("https://alloy-analyzer.onrender.com/api/favorites");
  });

  it("keeps relative API paths for local desktop development", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.stubGlobal("window", { location: { hostname: "localhost" } });
    vi.resetModules();

    const { apiUrl, hasConfiguredApiBaseUrl } = await import("./api.js");

    expect(apiUrl("/api/about")).toBe("/api/about");
    expect(hasConfiguredApiBaseUrl).toBe(false);
  });

  it("prefers an explicitly configured API origin", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test///");
    vi.stubGlobal("window", { location: { hostname: "alloy-analyzer.vercel.app" } });
    vi.resetModules();

    const { apiUrl } = await import("./api.js");

    expect(apiUrl("/api/about")).toBe("https://api.example.test/api/about");
  });
});
