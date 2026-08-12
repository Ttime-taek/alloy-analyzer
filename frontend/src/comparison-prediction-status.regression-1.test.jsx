import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import ComparisonPredictionStatus from "./ComparisonPredictionStatus.jsx";

describe("ComparisonPredictionStatus regression", () => {
  it("shows refused out-of-domain states instead of confidence alone", () => {
    // Regression: QA-001 — comparison hid out-of-domain/refused values behind 100% confidence.
    // Found by /qa on 2026-08-12
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    const contract = {
      family: "SAC",
      overall_state: "out_of_domain",
      overall_state_label_ko: "DB 범위 밖",
      overall_usage: "refused",
      overall_usage_label_ko: "사용 중단",
      properties: {
        tensile_strength_mpa: {
          state: "out_of_domain",
          state_label_ko: "DB 범위 밖",
          reason_labels_ko: ["검증 DB 범위를 벗어났습니다."]
        }
      }
    };

    const html = renderToStaticMarkup(
      <ComparisonPredictionStatus
        a={{ prediction_contract: contract }}
        b={{ prediction_contract: contract }}
      />
    );

    expect(html).toContain("비교 예측 사용 판정");
    expect(html).toContain("DB 범위 밖");
    expect(html).toContain("사용 중단");
    expect(html).toContain("비교 참고용으로도 사용을 중단하세요");
    expect(html).toContain('role="alert"');
  });
});
