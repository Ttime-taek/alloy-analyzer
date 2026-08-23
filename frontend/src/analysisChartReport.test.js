import { describe, it, expect } from "vitest";

import {

  compositionChartData,

  buildReportSlides,

  buildStandaloneAnalysisHtml

} from "./analysisChartReport.js";

import { extractBullets, summarizeLead, getResultNorm } from "./professionalReportSlides.js";



/** 실제 /api/analyze 응답 형태에 가깝게 */

const sampleResult = {

  solidus: 137.8,

  liquidus: 189.2,

  peak: 195.0,

  confidence_overall: 82.5,

  best_name: "Sn-Bi-Ag",

  norm: { Sn: 73.25, Bi: 25.0, Ag: 1.0, Cu: 0.75 },

  phase: "Bi 함량이 높아 Sn-Bi 저융점 상이 우세합니다.",

  imc: ["Cu6Sn5 (Cu 기판)", "Ag3Sn (Ag 함량 낮음)"],

  risk: ["열사이클 시 IMC 성장 주의", "Bi 함량 변동 시 고상선 민감"],

  ai_summary: "저융점 납땜에 적합하나 Bi 함량 관리가 중요합니다.",

  eng_report: "요약입니다.\n- IMC는 Cu-Sn 계열 확인",

  props: {
    wetting_by_temp: [
      { temp_c: 250, fmax_mn: 1.5, t0_s: 1.2 },
      { temp_c: 270, fmax_mn: 1.6, t0_s: 1.1 }
    ],
    tensile_strength: 100,
    tensile_strength_db_mpa: 72
  },

  alloy_inference: {
    solidus: 130,
    liquidus: 200,
    recommended_peak_c: 225,
    neighbors: [{ name: "Sn-Bi", weight: 0.9 }],
    process_report: "- 플라스틱 레인지 검토"
  },

  element_roles: "Sn: 기본 기지, Bi: 융점 저감",

  dopant_rec: "Cu 0.5~1% 유지 권장",

  // Process slides/charts are emitted only for an explicitly allowed contract.
  prediction_contract: {
    process_recommendation: { allowed: true }
  }

};



describe("analysisChartReport", () => {

  it("compositionChartData sorts Sn first", () => {

    const { labels } = compositionChartData(sampleResult.norm);

    expect(labels[0]).toBe("Sn");

  });



  it("getResultNorm prefers norm field", () => {

    expect(getResultNorm(sampleResult).Sn).toBe(73.25);

  });



  it("buildReportSlides maps API fields to brief slides", () => {

    const slides = buildReportSlides({ result: sampleResult, profile: null, melt: null });

    const kinds = slides.map((s) => s.kind);

    const titles = slides.map((s) => s.title);

    expect(kinds).toContain("cover");

    expect(kinds).toContain("executive");

    expect(kinds).toContain("metrics");

    expect(kinds).toContain("charts");

    expect(kinds).toContain("closing");

    expect(titles).toContain("분석 요약");

    expect(titles).toContain("상분석 · IMC");

    expect(titles).toContain("신뢰성 리스크 · AI");



    const phaseSlide = slides.find((s) => s.id === "brief-phase");

    expect(phaseSlide?.blocks?.some((b) => b.type === "bullets" && b.items?.length)).toBe(true);

    const wettingSlide = slides.find((s) => s.id === "brief-wetting");

    expect(wettingSlide?.blocks?.some((b) => b.type === "html" && b.html?.includes("pro-wetting-table"))).toBe(
      true
    );

    const infSlide = slides.find((s) => s.id === "brief-inference");

    expect(infSlide?.blocks?.[0]?.text).toContain("하이브리드 엔진");
    expect(
      infSlide?.blocks?.some(
        (b) => b.type === "bullets" && b.items?.some((x) => /3-NN|추론 모델|보간/.test(x))
      )
    ).toBe(true);

    const execSlide = slides.find((s) => s.id === "executive");

    expect(execSlide?.blocks?.[0]?.text).toContain("Bi");
    expect(execSlide?.blocks?.some((b) => b.type === "bullets" && b.items?.some((x) => /138\s*℃/.test(x)))).toBe(
      false
    );
  });



  it("standalone HTML includes slide layout classes", () => {

    const html = buildStandaloneAnalysisHtml({ result: sampleResult });

    expect(html).toContain("slide-head__title");

    expect(html).toContain("pro-kpi-grid");

  });

});



describe("professionalReportSlides", () => {

  it("extractBullets from list markers", () => {

    const b = extractBullets("- a\n- b\n- c");

    expect(b.length).toBe(3);

  });



  it("summarizeLead truncates long text", () => {

    const long = "가".repeat(300);

    expect(summarizeLead(long).length).toBeLessThan(230);

  });

});
