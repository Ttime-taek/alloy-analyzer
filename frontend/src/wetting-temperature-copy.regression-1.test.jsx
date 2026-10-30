// Regression: 2026-10-30 실행 점검 — 젖음 평가 온도는 이제 액상선+30℃(250–290℃ 범위로 제한)를
// 격자에 스냅하지 않고 쓰므로(예: SAC305 251℃), 정확일치 합금 카드도 측정 온도 사이 보간값이 된다.
// 화면 문구가 여전히 "가장 가까운 250–290℃ 값으로 맞춥니다", "등록 조성·온도의 직접 DB 기록"이라고 했다.
// Found by 운영 화면 직접 실행 점검 (Claude) on 2026-10-30
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { friendlyAiStatusMessage, wettingSourceDescription, wettingTemperatureInterpolated } from "./App.jsx";

function exactResult({ temp, interpolated, verified }) {
  return {
    solidus: 217,
    liquidus: 221,
    props: {
      wetting_fmax_pred_mn: 2.33,
      wetting_t0_pred_s: 0.69,
      wetting_temp_c: temp,
      wetting_temp_basis: "auto_liq_plus_30",
      wetting_metadata: {
        source_kind: "measured_db",
        value_type: verified ? "measured" : "direct_db_record",
        verification_status: verified ? "verified" : "unverified",
        comparison_allowed: verified,
        source_identifier: "wetting-series-test",
        comparison_basis: "auto_liq_plus_30",
        temperature_c: temp,
        temperature_interpolated: interpolated
      }
    },
    evidence: {
      wetting: {
        source_kind: "measured_db",
        value_type: verified ? "measured" : "direct_db_record",
        verification_status: verified ? "verified" : "unverified",
        comparison_allowed: verified,
        source_identifier: "wetting-series-test",
        comparison_basis: "auto_liq_plus_30",
        temperature_c: temp,
        temperature_basis: "auto_liq_plus_30"
      }
    }
  };
}

describe("wetting evaluation-temperature copy", () => {
  it("says an exact row between measured temperatures is interpolated", () => {
    const between = exactResult({ temp: 251, interpolated: true, verified: false });
    const onGrid = exactResult({ temp: 250, interpolated: false, verified: false });
    expect(wettingTemperatureInterpolated(between)).toBe(true);
    expect(wettingTemperatureInterpolated(onGrid)).toBe(false);
    expect(wettingSourceDescription(between)).toContain("보간");
    expect(wettingSourceDescription(between)).not.toContain("직접 DB 기록");
    expect(wettingSourceDescription(between)).toContain("원출처·시험조건 확인 전까지");
    expect(wettingSourceDescription(onGrid)).toContain("직접 DB 기록");
  });

  it("no longer describes the automatic temperature as snapped to the nearest grid value", () => {
    const source = readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
    expect(source).not.toContain("가장 가까운 250–290℃ 값으로 맞춥니다");
    expect(source).toContain("측정 온도 사이는 보간합니다");
  });
});

// Regression: 2026-10-30 실행 점검 — 운영 화면에 "Gemini 호출 오류 — Cerebras 폴백"만 보이고
// 원인(HTTP·상태 코드)을 알 수 없었다. 서버가 코드만 붙여 보내면 화면에도 같이 보인다.
describe("AI fallback status copy", () => {
  it("shows the Gemini error code when the server sends one", () => {
    expect(friendlyAiStatusMessage("Cerebras 폴백 사용 중 (Gemini 호출 오류: 403 PERMISSION_DENIED)")).toBe(
      "Gemini 호출 오류(403 PERMISSION_DENIED) — Cerebras 폴백으로 응답을 생성했습니다."
    );
    expect(friendlyAiStatusMessage("Cerebras 폴백 사용 중 (Gemini 호출 오류)")).toBe(
      "Gemini 호출 오류 — Cerebras 폴백으로 응답을 생성했습니다."
    );
    expect(friendlyAiStatusMessage("Cerebras 폴백 사용 중 (Gemini 쿼터 429)")).toContain("429");
  });
});
