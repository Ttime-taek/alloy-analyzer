/**
 * 리플로우 튜닝 — 수치·옵션 원천: ../../shared/reflow_tune_rules.json (Python 엔진과 동일 파일)
 */
import RULES from "../../shared/reflow_tune_rules.json";

export const TUNING_GOAL_OPTIONS = [...(RULES.tuningGoalOptions || [])];
export const REFLOW_TUNING_GOAL_STORAGE_KEY = "alloyReflowTuningGoal";

export function rulesVersion() {
  return Number(RULES.version || 1);
}

/** 프로필 preset 문자열 분류 — reflow_tune_engine.classify_preset 와 동일 */
export function classifyPreset(presetName) {
  const name = (presetName || "").trim();
  const isHighBi =
    !!name &&
    (name.startsWith("78") || name.includes("57.6Bi"));
  const isMidBi =
    !!name &&
    !isHighBi &&
    (name.startsWith("73") ||
      name.includes("15Bi") ||
      name.includes("25Bi") ||
      name.toLowerCase().includes("wide-paste"));

  let cat = "SAC";
  if (!name || name === "AUTO") cat = "SAC";
  else if (["SAC", "Sn-Cu", "Sn-Ag", "86", "90", "51", "92"].some((k) => name.startsWith(k))) {
    cat = "SAC";
  } else if (name.includes("Bi") || name.startsWith("78")) cat = "SnBi";
  else if (name.startsWith("Sn-In")) cat = "SnIn";
  else if (name.startsWith("Sn-Pb")) cat = "SnPb";
  else cat = "범용";

  return { cat, isHighBi, isMidBi };
}

/** @deprecated 이름 호환 — gui.py 의 _alloy_category_from_preset 과 동일 */
export function alloyCategoryFromPreset(presetName) {
  return classifyPreset(presetName).cat;
}

export function isHighBiPreset(presetName) {
  return classifyPreset(presetName).isHighBi;
}

export function isMidBiPreset(presetName) {
  return classifyPreset(presetName).isMidBi;
}

function _baseSnake(highBi, midBi, cat) {
  const b = RULES.bases;
  if (highBi) return { ...b.high_bi };
  if (midBi) return { ...b.mid_bi };
  if (cat === "SnBi") return { ...b.sn_bi };
  if (cat === "SnPb") return { ...b.sn_pb };
  return { ...b.default };
}

/** reflow_tune_engine._goal_profile_key 과 동일 */
function goalProfileKey(isHighBi, isMidBi) {
  if (isHighBi) return "high_bi";
  if (isMidBi) return "mid_bi";
  return "default";
}

/**
 * goalRecommendOps 한 줄 = [연산자, ...인자].
 * Python _apply_recommend_ops 와 시그니처·순서를 반드시 동일하게 유지할 것.
 */
function applyRecommendOps(rec, ops, ctx) {
  if (!Array.isArray(ops)) return;
  for (const raw of ops) {
    if (!raw || !Array.isArray(raw) || raw.length < 1) continue;
    const kind = raw[0];
    if (kind === "set") {
      rec[raw[1]] = Number(raw[2]);
    } else if (kind === "max") {
      const k = raw[1];
      rec[k] = Math.max(Number(rec[k]), Number(raw[2]));
    } else if (kind === "min") {
      const k = raw[1];
      rec[k] = Math.min(Number(rec[k]), Number(raw[2]));
    } else if (kind === "add_then_min") {
      const [k, a, c] = [raw[1], Number(raw[2]), Number(raw[3])];
      rec[k] = Math.min(c, Number(rec[k]) + a);
    } else if (kind === "floor_after_add") {
      const [k, a, f] = [raw[1], Number(raw[2]), Number(raw[3])];
      rec[k] = Math.max(f, Number(rec[k]) + a);
    } else if (kind === "max_minus") {
      const [k, m, fl] = [raw[1], Number(raw[2]), Number(raw[3])];
      rec[k] = Math.max(fl, Number(rec[k]) - m);
    } else if (kind === "clamp") {
      const [k, lo, hi] = [raw[1], Number(raw[2]), Number(raw[3])];
      const v = Number(rec[k]);
      rec[k] = Math.max(lo, Math.min(v, hi));
    } else if (kind === "min_add") {
      const [k, a, c] = [raw[1], Number(raw[2]), Number(raw[3])];
      rec[k] = Math.min(c, Number(rec[k]) + a);
    } else if (kind === "floor_after_subtract") {
      const [k, s, fl] = [raw[1], Number(raw[2]), Number(raw[3])];
      rec[k] = Math.max(fl, Number(rec[k]) - s);
    } else if (kind === "when_cat_equals") {
      const catNeed = raw[1];
      const sub = raw[2];
      if (ctx.cat === catNeed && Array.isArray(sub)) applyRecommendOps(rec, sub, ctx);
    } else if (kind === "merge") {
      const d = raw[1];
      if (d && typeof d === "object") {
        for (const kk of Object.keys(d)) rec[kk] = Number(d[kk]);
      }
    } else {
      throw new Error(`goalRecommendOps: unknown op ${String(kind)}`);
    }
  }
}

function snakeToCamelTune(s) {
  return {
    rampRate: Number(s.ramp_rate),
    preheatTime: Number(s.preheat_time),
    overLiquidusTime: Number(s.over_liquidus_time),
    coolRate: Number(s.cool_rate),
    peakMargin: Number(s.peak_margin)
  };
}

export function recommendTuneForGoal(goal, presetName) {
  const { cat, isHighBi, isMidBi } = classifyPreset(presetName);
  let base = _baseSnake(isHighBi, isMidBi, cat);
  base = { ...base };
  const g = String(goal || "없음").trim();

  if (g !== "없음") {
    const go = (RULES.goalRecommendOps || {})[g];
    if (go && typeof go === "object") {
      const pk = goalProfileKey(isHighBi, isMidBi);
      const ops = go[pk];
      applyRecommendOps(base, ops, { cat });
    }
  }

  Object.keys(base).forEach((k) => {
    base[k] = Math.round(Number(base[k]) * 100) / 100;
  });
  return snakeToCamelTune(base);
}

export function deviationHintAgainstRecommended(tuningGoal, rt, presetName) {
  if (!tuningGoal || tuningGoal === "없음") return null;
  const rec = recommendTuneForGoal(tuningGoal, presetName || "AUTO");
  const cur = rt || {};
  const items = [];
  const add = (key, shortLabel, decimals, thresh) => {
    const a = Number(cur[key]);
    const b = Number(rec[key]);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return;
    const d = a - b;
    if (Math.abs(d) < thresh) return;
    const fd = decimals === 0 ? d.toFixed(0) : d.toFixed(2);
    const sign = d > 0 ? "+" : "";
    items.push(`${shortLabel}${sign}${fd}`);
  };
  add("rampRate", "램프 ", 2, 0.05);
  add("preheatTime", "예열 ", 0, 1);
  add("overLiquidusTime", "TAL ", 0, 1);
  add("coolRate", "냉각 ", 2, 0.05);
  add("peakMargin", "Δ피크 ", 0, 0.5);
  return items.length ? items.join(" · ") : "(현재 수치가 목표별 권장값과 거의 동일)";
}

/** camelCase tune 검증 — reflow_tune_engine.validate_profile_tune 와 동일 메시지 */
export function validateProfileTune(tune, presetName) {
  const errors = [];
  const warnings = [];
  const oks = [];
  const { cat, isHighBi, isMidBi } = classifyPreset(presetName);
  const V = RULES.validation;
  const fatal = V.tal_fatal_lt;

  const ramp = Number(tune?.rampRate);
  const preheat = Number(tune?.preheatTime);
  const tal = Number(tune?.overLiquidusTime);
  const cool = Number(tune?.coolRate);
  const margin = Number(tune?.peakMargin);

  if (!Number.isFinite(tal)) {
    errors.push("TAL 값을 읽지 못함");
  } else if (isHighBi) {
    const hb = V.high_bi;
    if (tal < fatal) errors.push(`TAL ${tal.toFixed(0)}s < 25s — 젖음 부족 위험(공급사 가이드 위반)`);
    else if (tal < hb.tal_warn_lt) warnings.push(`TAL ${tal.toFixed(0)}s < 50s — 고-Bi 공급사 권장(50~100s) 미달`);
    else if (tal > hb.tal_warn_gt) warnings.push(`TAL ${tal.toFixed(0)}s > 100s — 과열/취성·탈색 위험(고-Bi)`);
    else oks.push(`TAL ${tal.toFixed(0)}s — 공급사 권장(50~100s) 영역`);
  } else if (isMidBi) {
    const mb = V.mid_bi;
    if (tal < fatal) errors.push(`TAL ${tal.toFixed(0)}s < 25s — 젖음 부족 위험(공급사 가이드 위반)`);
    else if (tal < mb.tal_warn_lt) warnings.push(`TAL ${tal.toFixed(0)}s < 50s — 중-Bi 공급사 권장(50~80s) 미달`);
    else if (tal > mb.tal_warn_gt) warnings.push(`TAL ${tal.toFixed(0)}s > 80s — wide-paste 합금 과도(슬럼프/취성 위험)`);
    else oks.push(`TAL ${tal.toFixed(0)}s — 공급사 권장(50~80s) 영역`);
  } else {
    const d = V.default;
    const talMax = cat === "SAC" ? d.tal_max_sac : cat === "SnBi" ? d.tal_max_sn_bi : d.tal_max_other;
    if (tal < fatal) errors.push(`TAL ${tal.toFixed(0)}s < 25s — 젖음 부족 위험(공급사 가이드 위반)`);
    else if (tal > talMax) warnings.push(`TAL ${tal.toFixed(0)}s > ${talMax}s — IMC 과성장/보이드 위험`);
    else oks.push(`TAL ${tal.toFixed(0)}s — 안전 범위`);
  }

  const rp = V.ramp;
  if (Number.isFinite(ramp)) {
    if (ramp < rp.warn_lt) warnings.push(`램프 ${ramp.toFixed(2)}℃/s — 너무 느림(가열 불균일/잔사 위험)`);
    else if (ramp > rp.warn_gt) warnings.push(`램프 ${ramp.toFixed(2)}℃/s — 너무 빠름(슬럼프/스패터 위험)`);
    else if (ramp >= rp.ok_low && ramp <= rp.ok_high) oks.push(`램프 ${ramp.toFixed(2)}℃/s — 공급사 권장 대역`);
  }

  const ph = V.preheat;
  if (Number.isFinite(preheat)) {
    if (isHighBi || isMidBi) {
      const label = isHighBi ? "고-Bi" : "중-Bi";
      if (preheat < ph.bi_fatal_lt) errors.push(`예열 ${preheat.toFixed(0)}s < 60s — ${label} 공급사 권장(60~120s) 미달`);
      else if (preheat > ph.bi_warn_gt) warnings.push(`예열 ${preheat.toFixed(0)}s > 120s — 산화/잔사 증가(${label})`);
      else if (preheat >= ph.bi_ok_low && preheat <= ph.bi_ok_high) {
        oks.push(`예열 ${preheat.toFixed(0)}s — 공급사 권장(90s) 부근`);
      }
    } else {
      if (preheat < ph.std_fatal_lt) errors.push(`예열 ${preheat.toFixed(0)}s < 60s — 플럭스 활성 부족`);
      else if (preheat > ph.std_warn_gt) warnings.push(`예열 ${preheat.toFixed(0)}s > 140s — 산화/잔사 증가`);
      else if (preheat >= ph.std_ok_low && preheat <= ph.std_ok_high) {
        oks.push(`예열 ${preheat.toFixed(0)}s — 공급사 권장(90s) 부근`);
      }
    }
  }

  const pm = V.peak_margin;
  if (Number.isFinite(margin)) {
    if (isHighBi) {
      if (margin < pm.high_bi_fatal_lt) errors.push(`피크 여유 ${margin.toFixed(0)}℃ < 30℃ — 미접합 위험(고-Bi)`);
      else if (margin > pm.high_bi_warn_gt) warnings.push(`피크 여유 ${margin.toFixed(0)}℃ > 55℃ — 과열/취성 위험(고-Bi)`);
      else if (margin >= pm.high_bi_ok_low && margin <= pm.high_bi_ok_high) {
        oks.push(`피크 여유 ${margin.toFixed(0)}℃ — 공급사 권장(36~51℃, peak 175~190℃) 영역`);
      }
    } else if (isMidBi) {
      if (margin < pm.mid_bi_fatal_lt) errors.push(`피크 여유 ${margin.toFixed(0)}℃ < 25℃ — 미접합 위험(중-Bi wide-paste)`);
      else if (margin > pm.mid_bi_warn_gt) warnings.push(`피크 여유 ${margin.toFixed(0)}℃ > 50℃ — 과열/IMC 과성장 위험(중-Bi)`);
      else if (margin >= pm.mid_bi_ok_low && margin <= pm.mid_bi_ok_high) {
        oks.push(`피크 여유 ${margin.toFixed(0)}℃ — 공급사 권장(30~44℃, peak 236~250℃) 영역`);
      }
    } else {
      if (margin < pm.default_fatal_lt) errors.push(`피크 여유 ${margin.toFixed(0)}℃ < 10℃ — 미접합 위험`);
      else if (margin > pm.default_warn_gt) warnings.push(`피크 여유 ${margin.toFixed(0)}℃ > 40℃ — 과열/IMC 과성장 위험`);
    }
  }

  const cw = V.cool;
  if (Number.isFinite(cool)) {
    if (cool > cw.warn_gt) warnings.push(`냉각 ${cool.toFixed(2)}℃/s > 4℃/s — 열충격/뒤틀림 위험`);
    else if (cool < cw.warn_lt) warnings.push(`냉각 ${cool.toFixed(2)}℃/s < 1℃/s — IMC 거대화 위험`);
  }
  return { errors, warnings, oks };
}

export function readReflowTuningGoalInitial() {
  try {
    if (typeof window === "undefined") return "없음";
    const v = window.localStorage.getItem(REFLOW_TUNING_GOAL_STORAGE_KEY);
    if (v && TUNING_GOAL_OPTIONS.includes(v)) return v;
  } catch {
    /* noop */
  }
  return "없음";
}
