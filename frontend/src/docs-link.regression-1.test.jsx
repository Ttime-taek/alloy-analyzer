import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

// Regression: ISSUE-001 — Swagger footer link resolved against the Vercel frontend.
// Found by /qa on 2026-07-15.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-15-2.md
describe("Swagger footer link", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("uses the configured API origin", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/");
    vi.resetModules();
    vi.spyOn(console, "error").mockImplementation(() => {});

    const { default: App } = await import("./App.jsx");
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('href="https://api.example.test/docs"');
    expect(html).not.toContain('href="/docs"');
  });
});
