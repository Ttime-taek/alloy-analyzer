// Regression: 2026-10-30 — 평가 온도가 측정 온도 사이(예: 251℃)면 온도별 젖음 표에서 강조되는 행이 없었다.
// 이제 정확히 같은 온도면 그 행, 사이면 양옆 두 행을 강조한다.
// Found by 운영 화면 직접 실행 점검 (Claude) on 2026-10-30
import { describe, expect, it } from "vitest";

import { wettingHighlightTemps } from "./App.jsx";

const rows = [250, 260, 270, 280, 290].map((t) => ({ temp_c: t, fmax_mn: 2, t0_s: 0.5 }));

describe("wetting table highlight", () => {
  it("highlights the exact row on a measured temperature", () => {
    expect([...wettingHighlightTemps(260, rows)]).toEqual([260]);
  });

  it("highlights the two bracketing rows between measured temperatures", () => {
    expect([...wettingHighlightTemps(251, rows)].sort()).toEqual([250, 260]);
    expect([...wettingHighlightTemps(285.2, rows)].sort()).toEqual([280, 290]);
  });

  it("highlights nothing without a temperature or outside the table", () => {
    expect(wettingHighlightTemps(null, rows).size).toBe(0);
    expect(wettingHighlightTemps(300, rows).size).toBe(0);
    expect(wettingHighlightTemps(255, []).size).toBe(0);
  });
});
