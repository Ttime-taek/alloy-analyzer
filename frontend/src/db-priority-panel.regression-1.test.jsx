import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import PredictionEvidencePanel from "./PredictionEvidencePanel.jsx";

describe("PredictionEvidencePanel DB-priority heading", () => {
  it("does not call an exact DB match a prediction", () => {
    const html = renderToStaticMarkup(
      <PredictionEvidencePanel contract={{ family: "SAC", overall_state: "exact_match", properties: {} }} />
    );
    expect(html).toContain("DB 등록값 우선");
    expect(html).not.toContain("예측 판정");
  });

  it("keeps the prediction heading for unregistered compositions", () => {
    const html = renderToStaticMarkup(
      <PredictionEvidencePanel contract={{ family: "SAC", overall_state: "in_domain", properties: {} }} />
    );
    expect(html).toContain("예측 판정");
  });
});
