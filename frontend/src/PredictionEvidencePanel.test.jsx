import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import PredictionEvidencePanel from "./PredictionEvidencePanel.jsx";

describe("PredictionEvidencePanel", () => {
  it("shows point, empirical range, state, and refused process action", () => {
    const html = renderToStaticMarkup(
      <PredictionEvidencePanel
        contract={{
          family: "SAC",
          overall_state: "out_of_domain",
          overall_state_label_ko: "DB 범위 밖",
          overall_usage_label_ko: "공정 추천 중단",
          properties: {
            liquidus_c: {
              point: 220.2,
              unit: "°C",
              interval: { lower: 185.0, upper: 255.4 },
              state: "out_of_domain",
              state_label_ko: "DB 범위 밖",
              usage_label_ko: "공정 추천 중단",
              evidence: { nearest_distance: 40.2 }
            }
          },
          process_recommendation: {
            allowed: false,
            usage_label_ko: "공정 추천 중단",
            recommended_peak_c: null,
            reason_labels_ko: ["검증 범위 밖이라 권장값을 내지 않습니다."]
          },
          disclaimer_ko: "시험을 대체하지 않습니다."
        }}
      />
    );

    expect(html).toContain("DB 범위 밖");
    expect(html).toContain("185.0–255.4 °C");
    expect(html).toContain("리플로우 사용 판정: 공정 추천 중단");
    expect(html).toContain("시험을 대체하지 않습니다.");
  });
});
