import { describe, expect, it } from "vitest";

import { isDbRegisteredMelt, meltSummaryHint } from "./App.jsx";

// Regression: 2026-09-21 — Sn-3Ag-0.5Cu (DB 221 ℃) was shown as "완전 액상(추정)",
// so a registered DB value looked like a model prediction.
const exact = {
  liquidus: 221,
  prediction_contract: {
    properties: {
      solidus_c: { point: 217, state: "exact_match" },
      liquidus_c: { point: 221, state: "exact_match" }
    }
  }
};
const predicted = {
  liquidus: 226.3,
  prediction_contract: {
    properties: {
      solidus_c: { point: 217, state: "in_domain" },
      liquidus_c: { point: 226.3, state: "in_domain" }
    }
  }
};

describe("DB-priority melting labels", () => {
  it("labels exact DB matches as DB registered values", () => {
    expect(isDbRegisteredMelt(exact, "liquidus_c")).toBe(true);
    expect(meltSummaryHint(exact, "liquidus")).toMatch(/DB 등록값/);
    expect(meltSummaryHint(exact, "solidus")).toMatch(/DB 등록값/);
    expect(meltSummaryHint(exact, "liquidus")).not.toMatch(/추정/);
  });

  it("keeps the estimate wording for predictions and the peak", () => {
    expect(meltSummaryHint(predicted, "liquidus")).toMatch(/추정/);
    expect(meltSummaryHint(exact, "peak")).toMatch(/추정/);
  });

  it("falls back to legacy melting_detail when no contract is present", () => {
    expect(isDbRegisteredMelt({ melting_detail: { db_exact_match: true } }, "liquidus_c")).toBe(true);
    expect(isDbRegisteredMelt({ melting_detail: { db_exact_match: false } }, "liquidus_c")).toBe(false);
  });
});
