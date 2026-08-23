import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SourceReferences, strengthSourceLine } from "./App.jsx";

describe("strength source provenance regression", () => {
  it("renders legacy strength numbers as unverified references without a source link", () => {
    const legacy = {
      alloy: "Sn3.0Ag0.5Cu",
      tensile_mpa: 48.5,
      shear_mpa: 84.5,
      source: "내부실측 DB 평균",
      source_kind: "legacy_internal_db_mean",
      value_type: "legacy_internal_db_mean",
      provenance_status: "unconfirmed",
      verification_status: "unverified",
      comparison_allowed: false,
      source_link_status: "unavailable"
    };

    const line = strengthSourceLine(legacy);
    expect(line).toContain("UTS≈48.5 MPa");
    expect(line).toContain("전단≈84.5 MPa");
    expect(line).toContain("레거시 내부 DB 평균");
    expect(line).toContain("원출처 링크 미확인 · 시험조건 미확인 · 참고 전용");
    expect(line).not.toContain("내부실측");

    const html = renderToStaticMarkup(
      <SourceReferences
        showAiCitations={false}
        result={{ evidence: { strength_literature: { refs: [legacy] } } }}
      />
    );
    expect(html).toContain("기계적 물성 출처·참고값");
    expect(html).toContain("원출처 링크 미확인 · 시험조건 미확인 · 참고 전용");
    expect(html).not.toContain("기계적 물성 문헌 참고");
    expect(html).not.toContain("href=");
  });

  it("keeps a real external literature DOI clickable without a missing-link warning", () => {
    const external = {
      alloy: "Sn3.0Ag0.5Cu",
      tensile_mpa: 40.95,
      source: "SAC305 인장 시험 (bulk solder)",
      citation: "Sn-Ag-Cu mechanical properties review",
      doi: "10.1515/pmp-2018-0006",
      url: "https://doi.org/10.1515/pmp-2018-0006"
    };

    const line = strengthSourceLine(external);
    expect(line).toContain("URL:https://doi.org/10.1515/pmp-2018-0006");
    expect(line).not.toContain("원출처 링크 미확인");

    const html = renderToStaticMarkup(
      <SourceReferences
        showAiCitations={false}
        result={{ evidence: { strength_literature: { refs: [external] } } }}
      />
    );
    expect(html).toContain('href="https://doi.org/10.1515/pmp-2018-0006"');
    expect(html).not.toContain("원출처 링크 미확인");
  });

  it("fails closed for a source-less reference while retaining its number", () => {
    const line = strengthSourceLine({ alloy: "fixture", tensile_mpa: 65 });

    expect(line).toContain("UTS≈65 MPa");
    expect(line).toContain("원출처 링크 미확인 · 시험조건 미확인 · 참고 전용");
  });
});
