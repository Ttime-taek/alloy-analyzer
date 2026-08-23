import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  OVERALL_CONFIDENCE_SCOPE_LABEL,
  PropertyBars,
  buildCompareHints,
  compareTensileMetric,
  mechanicalComparisonAllowed,
  mechanicalPropertySourceLabel,
  optionalFiniteNumber,
  tensileComparisonAllowed,
  tensileProvenanceWarning,
  tensileSummaryLabel,
  wettingComparisonAllowed,
  wettingSourceDescription,
  wettingSourceKind
} from "./App.jsx";
import { buildProfessionalReportSlides } from "./professionalReportSlides.js";
import PredictionEvidencePanel from "./PredictionEvidencePanel.jsx";

const REPORT = ".gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md";

function unverifiedMechanicalMetadata() {
  return Object.fromEntries(
    ["tensile_strength", "yield_strength", "elongation", "shear_strength"].map((key) => [
      key,
      {
        value_type: "legacy_measured_mean",
        source_type: "legacy_property_db",
        source_label: "DB(exact)",
        verification_status: "unverified",
        comparison_allowed: false
      }
    ])
  );
}

function compareResult({ sourceKind, valueType, verified, fmax, t0 }) {
  return {
    solidus: 200,
    liquidus: 210,
    props: {
      wetting_fmax_pred_mn: fmax,
      wetting_t0_pred_s: t0,
      wetting_temp_c: 250,
      wetting_temp_basis: "compare_shared",
      wetting_metadata: {
        source_kind: sourceKind,
        value_type: valueType,
        verification_status: verified ? "verified" : "unverified",
        comparison_allowed: verified,
        source_identifier: "wetting-series-test",
        comparison_basis: "compare_shared",
        temperature_c: 250
      },
      shear_strength: sourceKind === "measured_db" ? 84.5 : 28,
      yield_strength: sourceKind === "measured_db" ? 39.5 : 57,
      elongation: sourceKind === "measured_db" ? 48 : 17.5,
      tensile_strength_db_mpa: sourceKind === "measured_db" ? 48.5 : 78,
      mechanical_property_metadata: unverifiedMechanicalMetadata()
    },
    evidence: {
      wetting: {
        source_kind: sourceKind,
        value_type: valueType,
        verification_status: verified ? "verified" : "unverified",
        comparison_allowed: verified,
        source_identifier: "wetting-series-test",
        comparison_basis: "compare_shared",
        temperature_c: 250
      }
    }
  };
}

describe("property provenance safety regressions", () => {
  it("keeps real zero values while rendering missing values as missing", () => {
    // Regression: /qa ISSUE-002 — Number(null) exposed absent properties as a real 0.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    expect(REPORT).toContain("2026-08-17");
    expect(optionalFiniteNumber(null)).toBeNull();
    expect(optionalFiniteNumber(undefined)).toBeNull();
    expect(optionalFiniteNumber(" ")).toBeNull();
    expect(optionalFiniteNumber(false)).toBeNull();
    expect(optionalFiniteNumber(true)).toBeNull();
    expect(optionalFiniteNumber([])).toBeNull();
    expect(optionalFiniteNumber({})).toBeNull();
    expect(optionalFiniteNumber(0)).toBe(0);
    expect(optionalFiniteNumber("0")).toBe(0);
    expect(optionalFiniteNumber("1.25e2")).toBe(125);
    expect(tensileSummaryLabel({ tensile_strength_basis: "db_priority" })).toContain(
      "참고 전용"
    );
    expect(tensileProvenanceWarning({ props: {} })).toContain("근거 미확인");
  });

  it("shows unverified raw mechanical values without relative bars or ranking", () => {
    // Regression: /qa ISSUE-001 — legacy shear/yield/elongation/tensile DB values implied valid winners.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const a = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: null,
      t0: null
    });
    const b = compareResult({
      sourceKind: "measured_db",
      valueType: "measured",
      verified: true,
      fmax: null,
      t0: null
    });
    a.props.tensile_strength_lit_mpa = null;
    b.props.tensile_strength_lit_mpa = 0;

    const html = renderToStaticMarkup(<PropertyBars a={a} b={b} />);

    expect(html).toContain("전단 · DB 평균(시험조건 미확인) · 검증 미완료");
    expect(html).toContain("항복강도 · 검증 미완료");
    expect(html).toContain("연신율 · 검증 미완료");
    expect(html).toContain("물성 DB 인장 · 검증 미완료");
    expect(html).toContain("문헌 참고 인장 · 시험조건 미정규화/검증 미완료");
    expect(html).toContain("동일 시험법·조건 확인 전까지");
    expect(html).toContain("상대 막대·우열 비교 제외");
    expect(html).toContain("N/A");
    expect(html).toContain("0.0");
    expect(html).not.toContain("linear-gradient(90deg");
  });

  it("blocks wetting deltas and hints when prediction basis or verification differs", () => {
    // Regression: /qa ISSUE-003 — an IDW estimate and an exact measured DB value were ranked as peers.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const a = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: 1.94,
      t0: 1.09
    });
    const b = compareResult({
      sourceKind: "measured_db",
      valueType: "measured",
      verified: true,
      fmax: 2.32,
      t0: 0.71
    });

    expect(wettingSourceKind(a)).toBe("idw_prediction");
    expect(wettingSourceKind(b)).toBe("measured_db");
    expect(wettingComparisonAllowed(a, b)).toBe(false);
    expect(buildCompareHints(a, b)).toEqual([]);

    const html = renderToStaticMarkup(<PropertyBars a={a} b={b} />);
    expect(html).toContain("A IDW 예측(검증 보류) / B 측정 DB");
    expect(html).toContain("근거·검증 상태가 달라 상대 막대 생략");
  });

  it("carries N/A and provenance warnings into the professional report", () => {
    // Regression: /qa ISSUE-004 — exported reports lost source and verification limits.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const result = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: 1.94,
      t0: 1.09
    });
    result.norm = { Sn: 93.5, Ag: 3, Cu: 0.5, Bi: 3 };
    result.peak = 240;
    result.props.tensile_strength = null;
    result.props.tensile_strength_db_mpa = null;
    result.props.yield_strength = null;
    result.props.elongation = null;
    result.props.shear_strength = null;

    const serialized = JSON.stringify(buildProfessionalReportSlides({ result }));

    expect(serialized).toContain("젖음 (IDW 예측)");
    expect(serialized).toContain("검증 미완료 · 우열/추천 제외");
    expect(serialized).toContain("물성 DB 인장 · 검증 미완료");
    expect(serialized).toContain("N/A");
    expect(serialized).not.toContain("0.0 MPa");
  });

  it("keeps an unverified wetting source classification in exported reports", () => {
    // Regression: /qa ISSUE-013 — strict verification accidentally erased known
    // measured-vs-IDW source classification from reference-only report values.
    // Found by /qa 2026-08-21
    const result = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: false,
      fmax: 2.32,
      t0: 0.71
    });
    result.norm = { Sn: 96.5, Ag: 3, Cu: 0.5 };
    result.peak = 241;
    delete result.props.wetting_metadata.source_identifier;
    delete result.props.wetting_metadata.comparison_basis;
    delete result.evidence.wetting.source_identifier;
    delete result.evidence.wetting.comparison_basis;

    const serialized = JSON.stringify(buildProfessionalReportSlides({ result }));

    expect(serialized).toContain("젖음 (측정 DB)");
    expect(serialized).toContain("검증 미완료 · 우열/추천 제외");
    expect(serialized).not.toContain("젖음 (근거 미확인)");
  });

  it("lets mechanical provenance override exact-match confidence for final tensile comparison", () => {
    // Regression: /qa ISSUE-005 — exact prediction-contract state re-enabled B−A for unverified tensile data.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const a = compareResult({
      sourceKind: "measured_db",
      valueType: "measured",
      verified: true,
      fmax: 2.1,
      t0: 0.8
    });
    const b = compareResult({
      sourceKind: "measured_db",
      valueType: "measured",
      verified: true,
      fmax: 2.2,
      t0: 0.7
    });
    a.props.tensile_strength = 78;
    b.props.tensile_strength = 48.5;
    a.props.tensile_strength_basis = "db_priority";
    b.props.tensile_strength_basis = "db_priority";
    const exactContract = {
      overall_state: "exact_match",
      properties: { tensile_strength_mpa: { state: "exact_match" } }
    };
    a.prediction_contract = exactContract;
    b.prediction_contract = exactContract;

    const metric = compareTensileMetric(a, b);

    expect(metric.valueA).toBe(78);
    expect(metric.valueB).toBe(48.5);
    expect(tensileComparisonAllowed(a, b)).toBe(false);
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    expect(tensileSummaryLabel(a.props)).toContain("참고 전용");
    expect(tensileProvenanceWarning(a)).toContain("시험조건·원출처 미확인");
  });

  it("labels shear from metadata instead of assuming every value is an internal DB value", () => {
    // Regression: /qa ISSUE-006 — model and IDW shear values were mislabeled as internal DB measurements.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const legacy = compareResult({
      sourceKind: "measured_db",
      valueType: "measured",
      verified: true,
      fmax: null,
      t0: null
    });
    const idw = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: null,
      t0: null
    });
    idw.props.mechanical_property_metadata.shear_strength = {
      value_type: "idw_prediction",
      source_type: "legacy_property_db",
      source_label: "DB(IDW,d=2.4)",
      verification_status: "unverified",
      comparison_allowed: false
    };
    idw.props.shear_metadata = idw.props.mechanical_property_metadata.shear_strength;
    idw.props.shear_strength_basis = "db_idw";
    const model = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: null,
      t0: null
    });
    model.props.mechanical_property_metadata.shear_strength = {
      value_type: "model_prediction",
      source_type: "model",
      source_label: "MODEL",
      verification_status: "unverified",
      comparison_allowed: false
    };

    expect(mechanicalPropertySourceLabel(legacy, "shear_strength")).toBe(
      "DB 평균(시험조건 미확인)"
    );
    expect(mechanicalPropertySourceLabel(idw, "shear_strength")).toBe("DB IDW 예측");
    expect(mechanicalPropertySourceLabel(model, "shear_strength")).toBe("모델 예측");

    const html = renderToStaticMarkup(<PropertyBars a={legacy} b={idw} />);
    expect(html).toContain("A DB 평균(시험조건 미확인) / B DB IDW 예측");

    model.norm = { Sn: 96.5, Ag: 3, Cu: 0.5 };
    model.peak = 240;
    const serialized = JSON.stringify(buildProfessionalReportSlides({ result: model }));
    expect(serialized).toContain("전단 · 모델 예측");
  });

  it("scopes confidence and keeps exact wetting copy measurement-only", () => {
    // Regression: /qa ISSUE-007 — overall confidence looked like mechanical validation and exact wetting mixed IDW copy.
    // Found by /qa 2026-08-17
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const exact = compareResult({
      sourceKind: "measured_db",
      valueType: "measured",
      verified: true,
      fmax: 2.32,
      t0: 0.71
    });
    const predicted = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: 1.94,
      t0: 1.09
    });
    const unverifiedExact = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: false,
      fmax: 2.32,
      t0: 0.71
    });

    expect(OVERALL_CONFIDENCE_SCOPE_LABEL).toBe("조성·융점/젖음 근거 신뢰도");
    expect(wettingSourceDescription(exact)).toContain("측정값");
    expect(wettingSourceDescription(exact)).not.toContain("IDW");
    expect(wettingSourceDescription(unverifiedExact)).toContain("원출처·시험조건 확인 전까지");
    expect(wettingSourceDescription(predicted)).toContain("IDW 보간");

    exact.norm = { Sn: 96.5, Ag: 3, Cu: 0.5 };
    exact.peak = 240;
    exact.confidence_overall = 85;
    exact.props.tensile_strength = 48.5;
    exact.props.tensile_strength_basis = "db_priority";
    const serialized = JSON.stringify(buildProfessionalReportSlides({ result: exact }));
    expect(serialized).toContain("조성·융점/젖음 근거 신뢰도");
    expect(serialized).toContain("인장 · 참고 전용");
    expect(serialized).toContain("시험조건·원출처 미확인/검증 미완료");
  });

  it("shows the tensile provenance comparison gate in the prediction contract card", () => {
    // Regression: /qa ISSUE-008 — exact composition status hid the independent provenance gate.
    // Found by /qa 2026-08-21
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const contract = {
      family: "SAC",
      overall_state: "exact_match",
      overall_state_label_ko: "DB 등록값",
      overall_usage_label_ko: "참고 가능",
      properties: {
        tensile_strength_mpa: {
          point: 48.5,
          unit: "MPa",
          state: "exact_match",
          state_label_ko: "DB 등록값",
          usage_label_ko: "참고 가능",
          evidence: { nearest_distance: 0 },
          comparison_allowed: false,
          comparison_label_ko: "시험조건 확인 전까지 정량 비교 금지"
        }
      },
      process_recommendation: { allowed: true, usage_label_ko: "일반 참고값" }
    };

    const html = renderToStaticMarkup(<PredictionEvidencePanel contract={contract} />);
    expect(html).toContain("시험조건 확인 전까지 정량 비교 금지");
  });

  it("does not render malformed prediction-contract values as real zero", () => {
    // Regression: /qa ISSUE-012 — booleans and arrays crossed the UI number boundary as 0.
    // Found by /qa 2026-08-21
    const contract = {
      family: "SAC",
      overall_state: "unavailable",
      overall_state_label_ko: "예측 불가",
      overall_usage_label_ko: "사용 중단",
      properties: {
        tensile_strength_mpa: {
          point: false,
          unit: "MPa",
          state: "unavailable",
          state_label_ko: "예측 불가",
          usage_label_ko: "사용 중단",
          interval: { lower: [], upper: [0] },
          evidence: { nearest_distance: {} },
          comparison_allowed: false
        }
      },
      process_recommendation: { allowed: false, recommended_peak_c: false }
    };

    const html = renderToStaticMarkup(<PredictionEvidencePanel contract={contract} />);
    expect(html).toContain("N/A");
    expect(html).not.toContain("0.0 MPa");
    expect(html).not.toContain("기준 피크 0.0");
  });

  it("fails closed on malformed provenance and opens only for explicit matching identities", () => {
    // Regression: /qa ISSUE-009 — malformed or identity-free metadata could reopen comparisons.
    // Found by /qa 2026-08-21
    // Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md
    const a = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: true,
      fmax: 2.1,
      t0: 0.8
    });
    const b = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: true,
      fmax: 2.2,
      t0: 0.7
    });
    a.props.wetting_metadata.value_type = { malformed: true };
    b.props.wetting_metadata.value_type = { malformed: true };
    a.evidence.wetting = a.props.wetting_metadata;
    b.evidence.wetting = b.props.wetting_metadata;
    expect(wettingComparisonAllowed(a, b)).toBe(false);

    const malformedMechanical = {
      comparison_allowed: true,
      verification_status: "verified",
      source_type: { malformed: true },
      value_type: { malformed: true },
      source_identifier: "same-source",
      comparison_basis: "same-method"
    };
    a.props.mechanical_property_metadata.tensile_strength = malformedMechanical;
    b.props.mechanical_property_metadata.tensile_strength = { ...malformedMechanical };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);

    const verifiedMechanical = {
      comparison_allowed: true,
      verification_status: "verified",
      source_type: "verified_property_db",
      value_type: "verified_measured_mean",
      source_identifier: "series-42",
      comparison_basis: "same-specimen-and-method"
    };
    a.props.mechanical_property_metadata.tensile_strength = verifiedMechanical;
    b.props.mechanical_property_metadata.tensile_strength = { ...verifiedMechanical };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    a.props.tensile_strength = 48.5;
    b.props.tensile_strength = 49.0;
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(true);
    a.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      source_type: "literature",
      value_type: "measured"
    };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    a.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      source_id: "conflicting-series"
    };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    a.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      source_identifier: "Lot-A"
    };
    b.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      source_identifier: "lot a"
    };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    a.props.mechanical_property_metadata.tensile_strength = verifiedMechanical;
    b.props.mechanical_property_metadata.tensile_strength = { ...verifiedMechanical };
    a.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      source_type: "Verified Property DB",
      value_type: "verified-measured-mean",
      verification_status: "VERIFIED"
    };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    a.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      comparison_basis: "method-A"
    };
    b.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      comparison_basis: "method A"
    };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    a.props.mechanical_property_metadata.tensile_strength = verifiedMechanical;
    b.props.mechanical_property_metadata.tensile_strength = { ...verifiedMechanical };
    a.prediction_contract = {
      properties: { tensile_strength_mpa: { comparison_allowed: false } }
    };
    b.prediction_contract = {
      properties: { tensile_strength_mpa: { comparison_allowed: true } }
    };
    expect(tensileComparisonAllowed(a, b)).toBe(false);
    a.prediction_contract = { properties: {} };
    expect(tensileComparisonAllowed(a, b)).toBe(false);
    delete a.prediction_contract;
    delete b.prediction_contract;
    a.props.mechanical_property_metadata.tensile_strength = verifiedMechanical;
    a.evidence.mechanical_properties = {
      tensile_strength: { ...verifiedMechanical, verification_status: "unverified" }
    };
    expect(mechanicalComparisonAllowed(a, b, "tensile_strength")).toBe(false);
    expect(tensileProvenanceWarning(a)).toContain("검증 미완료");
    delete a.evidence.mechanical_properties;

    a.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical,
      source_identifier: ""
    };
    expect(tensileProvenanceWarning(a)).toContain("검증 미완료");
    a.props.mechanical_property_metadata.tensile_strength = verifiedMechanical;

    const malformedContainerA = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: false,
      fmax: null,
      t0: null
    });
    const malformedContainerB = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: false,
      fmax: null,
      t0: null
    });
    malformedContainerA.props.mechanical_property_metadata = [];
    malformedContainerA.evidence.mechanical_properties = {
      tensile_strength: { ...verifiedMechanical }
    };
    malformedContainerB.props.mechanical_property_metadata.tensile_strength = {
      ...verifiedMechanical
    };
    expect(
      mechanicalComparisonAllowed(malformedContainerA, malformedContainerB, "tensile_strength")
    ).toBe(false);

    for (const result of [a, b]) {
      result.props.mechanical_property_metadata.shear_strength = { ...verifiedMechanical };
      result.props.shear_metadata = { ...verifiedMechanical };
      result.evidence.mechanical_properties = {
        ...(result.evidence.mechanical_properties || {}),
        shear_strength: { ...verifiedMechanical }
      };
    }
    expect(mechanicalComparisonAllowed(a, b, "shear_strength")).toBe(true);
    a.props.shear_metadata = { ...verifiedMechanical, verification_status: "unverified" };
    expect(mechanicalComparisonAllowed(a, b, "shear_strength")).toBe(false);

    const verifiedWetting = {
      source_kind: "measured_db",
      value_type: "direct_db_record",
      verification_status: "verified",
      comparison_allowed: true,
      source_identifier: "wetting-series-7",
      comparison_basis: "compare_shared",
      temperature_c: 250
    };
    a.props.wetting_metadata = verifiedWetting;
    b.props.wetting_metadata = { ...verifiedWetting };
    a.evidence.wetting = verifiedWetting;
    b.evidence.wetting = { ...verifiedWetting };
    expect(wettingComparisonAllowed(a, b)).toBe(true);

    a.evidence.wetting = { ...verifiedWetting, temperature_c: null };
    expect(wettingComparisonAllowed(a, b)).toBe(false);
    a.evidence.wetting = { ...verifiedWetting };
    a.props.wetting_metadata = {
      ...verifiedWetting,
      source_kind: "Measured DB",
      value_type: "direct-db-record",
      verification_status: "VERIFIED",
      comparison_basis: "compare-shared"
    };
    a.evidence.wetting = { ...a.props.wetting_metadata };
    expect(wettingComparisonAllowed(a, b)).toBe(false);
    expect(wettingSourceKind(a)).toBe("legacy_unverified");
    a.props.wetting_metadata = { ...verifiedWetting };
    a.evidence.wetting = {
      ...verifiedWetting,
      source_kind: "idw_prediction",
      value_type: "idw_prediction"
    };
    expect(wettingSourceKind(a)).toBe("legacy_unverified");
    expect(wettingComparisonAllowed(a, b)).toBe(false);

    a.evidence.wetting = { ...verifiedWetting, verification_status: "unverified" };
    expect(wettingComparisonAllowed(a, b)).toBe(false);
    a.evidence.wetting = { ...verifiedWetting };
    a.props.wetting_metadata = { ...verifiedWetting, comparison_allowed: false };
    expect(wettingComparisonAllowed(a, b)).toBe(false);
    a.props.wetting_metadata = { ...verifiedWetting, comparison_basis: { bad: true } };
    a.evidence.wetting = { ...a.props.wetting_metadata };
    expect(wettingComparisonAllowed(a, b)).toBe(false);
    a.props.wetting_metadata = { ...verifiedWetting };
    a.evidence.wetting = { ...verifiedWetting, source_id: "conflicting-wetting-series" };
    expect(wettingComparisonAllowed(a, b)).toBe(false);

    const malformedReport = compareResult({
      sourceKind: "idw_prediction",
      valueType: "idw_prediction",
      verified: false,
      fmax: false,
      t0: []
    });
    malformedReport.norm = { Sn: 100 };
    malformedReport.props.tensile_strength = false;
    malformedReport.props.shear_strength = [];
    malformedReport.props.mechanical_property_metadata.tensile_strength = verifiedMechanical;
    malformedReport.evidence.mechanical_properties = {
      tensile_strength: { ...verifiedMechanical, verification_status: "unverified" }
    };
    const serialized = JSON.stringify(buildProfessionalReportSlides({ result: malformedReport }));
    expect(serialized).toContain("N/A");
    expect(serialized).not.toContain("0.0 MPa");
    expect(serialized).toContain("검증 미완료");
  });

  it("fails closed on string booleans and missing process contracts", () => {
    const result = compareResult({
      sourceKind: "measured_db",
      valueType: "direct_db_record",
      verified: false,
      fmax: 2.32,
      t0: 0.71
    });
    result.norm = { Sn: 96.5, Ag: 3, Cu: 0.5 };
    result.peak = 241;
    result.prediction_contract = {
      process_recommendation: { allowed: "false", usage_label_ko: "확인 필요" },
      properties: {
        tensile_strength_mpa: {
          point: 48.5,
          unit: "MPa",
          state: "exact_match",
          state_label_ko: "DB 등록값",
          usage_label_ko: "참고 가능",
          evidence: {},
          comparison_allowed: "false"
        }
      }
    };

    const evidenceHtml = renderToStaticMarkup(
      <PredictionEvidencePanel contract={result.prediction_contract} />
    );
    expect(evidenceHtml).toContain("리플로우 사용 판정");
    expect(evidenceHtml).toContain("정량 비교 금지");

    const slides = buildProfessionalReportSlides({ result });
    expect(slides.some((slide) => slide.id === "charts")).toBe(false);
    expect(slides.some((slide) => slide.id === "process-refused")).toBe(true);
  });
});
