import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchApi } from "./api.js";

// Regression: QA-002 — first analysis request failed while the Render service woke.
// Found by /qa on 2026-07-15.
// Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-15.md
describe("fetchApi cold-start retry", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("retries a transient gateway response and returns the successful response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await fetchApi("/api/analyze", {}, { retryDelays: [0] });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries a temporary network failure", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await fetchApi("/api/compare", {}, { retryDelays: [0] });

    expect(response.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
