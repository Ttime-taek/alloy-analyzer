import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ComparisonSources,
  SourceReferences,
  sourceLinkFromString
} from "./App.jsx";

describe("analysis source links regression", () => {
  it("turns bare HTTPS and DOI references into safe links", () => {
    expect(sourceLinkFromString("https://doi.org/10.1000/fixture").href).toBe(
      "https://doi.org/10.1000/fixture"
    );
    expect(sourceLinkFromString("paper DOI:10.1000/fixture").href).toBe(
      "https://doi.org/10.1000/fixture"
    );
    expect(sourceLinkFromString("URL:javascript:alert(1)").href).toBeNull();
  });

  it("renders standards, strength literature, and candidates as clickable sources", () => {
    const html = renderToStaticMarkup(
      <SourceReferences
        result={{
          ai_source: "not_requested",
          evidence: {
            standards_refs: [
              {
                family: "IPC",
                id: "J-STD-006",
                note: "fixture standard",
                url: "https://www.ipc.org/ipc-standards"
              }
            ],
            strength_literature: {
              refs: [
                {
                  alloy: "SAC305",
                  tensile_mpa: 40.95,
                  source: "fixture paper",
                  doi: "10.1515/pmp-2018-0006"
                }
              ]
            }
          },
          ai_cited_sources: [],
          retrieved_candidates: ["https://doi.org/10.1000/fixture"]
        }}
      />
    );

    expect(html).toContain('href="https://www.ipc.org/ipc-standards"');
    expect(html).toContain('href="https://doi.org/10.1515/pmp-2018-0006"');
    expect(html).toContain('href="https://doi.org/10.1000/fixture"');
    expect(html).toContain("AI 설명을 불러오면");
  });

  it("shows deduplicated source evidence in comparison results", () => {
    const common = {
      evidence: {
        standards_refs: [
          {
            family: "JIS",
            id: "Z 3198",
            note: "fixture standard",
            url: "https://www.jisc.go.jp/"
          }
        ]
      },
      retrieved_candidates: ["https://doi.org/10.1000/shared"]
    };
    const html = renderToStaticMarkup(<ComparisonSources a={common} b={common} />);

    expect(html).toContain("A·B 분석 참고");
    expect(html.match(/href="https:\/\/doi.org\/10.1000\/shared"/g)).toHaveLength(1);
  });
});
