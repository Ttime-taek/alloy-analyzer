import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { meltSummaryHint } from "./App.jsx";
import PredictionEvidencePanel from "./PredictionEvidencePanel.jsx";

// Regression: 2026-09-25 계산 로직 점검 — Sn43Pb43Bi14(실측 144/163 ℃)는 판정 패널에서
// "DB 범위 밖 · 사용 중단"이었지만, 같은 카드에 "경험적 90% 범위 182.7–183.3 ℃"(±0.3 ℃)가 붙고
// KPI 타일은 183/212/237 ℃를 "(추정)"만 달고 강조해 쓸 수 있는 값처럼 보였다.
const outOfDomain = {
  solidus: 183.0,
  liquidus: 212.0,
  peak: 237.0,
  prediction_contract: {
    family: "Pb-alloy",
    overall_state: "out_of_domain",
    overall_usage: "refused",
    properties: {
      solidus_c: { point: 183.0, unit: "°C", interval: null, state: "out_of_domain" },
      liquidus_c: { point: 212.0, unit: "°C", interval: null, state: "out_of_domain" }
    }
  }
};

describe("out-of-domain melting display", () => {
  it("marks KPI tiles as refused instead of a plain estimate", () => {
    expect(meltSummaryHint(outOfDomain, "solidus")).toMatch(/DB 범위 밖 · 사용 중단/);
    expect(meltSummaryHint(outOfDomain, "liquidus")).toMatch(/DB 범위 밖 · 사용 중단/);
    expect(meltSummaryHint(outOfDomain, "peak")).toMatch(/공정 권장 중단/);
  });

  it("keeps the normal estimate wording for in-domain predictions", () => {
    const inDomain = {
      prediction_contract: {
        properties: {
          solidus_c: { state: "in_domain" },
          liquidus_c: { state: "in_domain" }
        }
      }
    };
    expect(meltSummaryHint(inDomain, "solidus")).toBe("응고가 시작되는 쪽 온도(추정)");
    expect(meltSummaryHint(inDomain, "peak")).toBe("DSC/DTA 등 주요 열역학 신호(추정)");
  });

  it("says the range cannot be estimated when out of domain has no interval", () => {
    const html = renderToStaticMarkup(
      React.createElement(PredictionEvidencePanel, {
        contract: {
          ...outOfDomain.prediction_contract,
          overall_state_label_ko: "DB 범위 밖",
          properties: {
            solidus_c: {
              ...outOfDomain.prediction_contract.properties.solidus_c,
              state_label_ko: "DB 범위 밖",
              usage_label_ko: "사용 중단",
              evidence: { nearest_distance: 36.3 }
            }
          },
          process_recommendation: { allowed: false, usage_label_ko: "공정 추천 중단" }
        }
      })
    );
    expect(html).toContain("산정 불가 (검증 범위 밖)");
    expect(html).not.toContain("182.7");
  });
});
