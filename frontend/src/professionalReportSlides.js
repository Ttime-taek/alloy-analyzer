/**

 * 분석 결과 → 발표용 슬라이드 (API 응답 필드와 UI 패널 구조에 맞춤)

 */



function fmtNum(v, digits = 1) {

  const n = Number(v);

  return Number.isFinite(n) ? n.toFixed(digits) : "—";

}



/** API /analyze 응답의 조성 객체 (norm 우선) */

export function getResultNorm(result) {

  return result?.norm || result?.composition_normalized || result?.composition || {};

}



/** 문장·목록에서 발표용 불릿 추출 */

export function extractBullets(text, max = 6) {

  const t = String(text || "").trim();

  if (!t || t === "N/A") return [];

  const lines = t.split(/\n/).map((l) => l.trim()).filter(Boolean);

  const fromMarkers = lines

    .filter((l) => /^[-•·*]\s/.test(l) || /^\d+[.)]\s/.test(l))

    .map((l) => l.replace(/^[-•·*]\s+/, "").replace(/^\d+[.)]\s+/, "").trim());

  if (fromMarkers.length >= 1) return fromMarkers.slice(0, max);

  const flat = t.replace(/\n+/g, " ");

  const sentences = flat.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter((s) => s.length > 12);

  if (sentences.length >= 2) return sentences.slice(0, max);

  if (flat.length > 180) return [`${flat.slice(0, 177)}…`];

  return flat ? [flat] : [];

}



/** 슬라이드 상단 리드 문장 */

export function summarizeLead(text, maxLen = 220) {

  const t = String(text || "").trim();

  if (!t || t === "N/A") return "";

  const one = t.replace(/\s+/g, " ");

  if (one.length <= maxLen) return one;

  const cut = one.slice(0, maxLen);

  const last = cut.lastIndexOf(" ");

  return `${(last > 80 ? cut.slice(0, last) : cut).trim()}…`;

}



function stripReportDecor(text) {

  return String(text || "")

    .replace(/={3,}/g, "\n")

    .replace(/^\s*[*]\s*/gm, "")

    .replace(/\n{3,}/g, "\n\n")

    .trim();

}

function toPlainLines(text) {
  return String(text || "")
    .split(/\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

function extractEngBullets(engText, max = 6) {
  const lines = toPlainLines(engText);
  const bullets = lines
    .filter((l) => /^[-•·*]\s/.test(l) || /^\d+[.)]\s/.test(l))
    .map((l) => l.replace(/^[-•·*]\s+/, "").replace(/^\d+[.)]\s+/, "").trim());
  return bullets.slice(0, max);
}

function techSummaryLead(result, meta) {
  const best = result?.best_name ? ` · DB 매칭: ${result.best_name}` : "";
  const conf = Number.isFinite(Number(result?.confidence_overall))
    ? ` · 종합 신뢰도 ${fmtNum(result?.confidence_overall, 0)}%`
    : "";
  const s = Number(result?.solidus);
  const l = Number(result?.liquidus);
  const p = Number(result?.peak);
  const range = Number.isFinite(s) && Number.isFinite(l) ? ` (Δ ${fmtNum(l - s, 1)} ℃)` : "";
  return `조성 ${meta.composition} 기준 추정 융점: 고상선 ${fmtNum(s)} ℃, 액상선 ${fmtNum(l)} ℃${range}, 계산 피크(참고) ${fmtNum(p)} ℃.${best}${conf}`;
}

function fmtMaybe(v, digits = 1) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : null;
}

function shortWettingBasis(basis) {
  const b = String(basis || "").trim();
  if (!b) return "";
  if (b === "auto_liq_plus_30") return "+30℃(Liq)";
  if (b === "compare_shared") return "비교 공통";
  if (b === "auto") return "auto";
  return b.replace(/_/g, " ");
}

function buildPropsKpis(result) {
  const props = result?.props || {};
  const kpis = [];

  const fmax = fmtMaybe(props?.wetting_fmax_pred_mn, 2);
  const t0 = fmtMaybe(props?.wetting_t0_pred_s, 2);
  const tc = fmtMaybe(props?.wetting_temp_c, 0);
  const basis = String(props?.wetting_temp_basis || "").trim();
  if (fmax) {
    let hint = "";
    if (t0) hint += `T0 ${t0}s`;
    if (tc) hint += `${hint ? " / " : ""}${tc}℃`;
    const sb = shortWettingBasis(basis);
    if (sb) hint += `${hint ? " · " : ""}${sb}`;
    kpis.push({ label: "젖음", value: `Fmax ${fmax} mN`, hint: hint || undefined });
  }

  const tensileBasis = props?.tensile_strength_basis;
  const tensile = fmtMaybe(props?.tensile_strength, 1);
  if (tensile) {
    let tLabel = "인장";
    if (tensileBasis === "db_idw") tLabel = "인장 (BD유사)";
    else if (tensileBasis === "lit_ref") tLabel = "인장 (문헌)";
    else if (tensileBasis === "lit_blend") tLabel = "인장 (문헌보정)";
    else if (tensileBasis === "db_blend") tLabel = "인장 (BD블렌드)";
    kpis.push({ label: tLabel, value: `${tensile} MPa` });
  } else {
    const tdb = fmtMaybe(props?.tensile_strength_db_mpa, 1);
    if (tdb) kpis.push({ label: "물성 DB 인장", value: `${tdb} MPa` });
  }

  const shearBasis = props?.shear_strength_basis;
  const shear = fmtMaybe(props?.shear_strength, 1);
  if (shear) {
    const sLabel = shearBasis === "db_idw" ? "전단 (BD유사)" : "전단";
    kpis.push({ label: sLabel, value: `${shear} MPa` });
  }

  const ys = fmtMaybe(props?.yield_strength, 1);
  if (ys) kpis.push({ label: "예측 항복", value: `${ys} MPa` });

  const el = fmtMaybe(props?.elongation, 1);
  if (el) kpis.push({ label: "연신율", value: `${el} %` });

  return kpis;
}

function renderKpiCellsHtml(items) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return "";
  const cells = list
    .map((k) => {
      const hint = k.hint ? `<span class="pro-kpi__hint">${escapeHtml(k.hint)}</span>` : "";
      return `<div class="pro-kpi">
  <span class="pro-kpi__label">${escapeHtml(k.label)}</span>
  <span class="pro-kpi__value">${escapeHtml(k.value)}</span>
  ${hint}
</div>`;
    })
    .join("");
  return `<div class="pro-kpi-grid">${cells}</div>`;
}

function getWettingByTempRows(result) {
  const rows = result?.props?.wetting_by_temp;
  return Array.isArray(rows) ? rows.filter((r) => r && r.temp_c != null) : [];
}

function renderWettingTableHtml(rows) {
  const head =
    "<thead><tr><th>온도 (℃)</th><th>Fmax (mN)</th><th>T0 (s)</th></tr></thead>";
  const body = rows
    .map(
      (r) =>
        `<tr><td>${escapeHtml(String(r.temp_c))}</td><td>${fmtNum(r.fmax_mn, 2)}</td><td>${fmtNum(r.t0_s, 2)}</td></tr>`
    )
    .join("");
  return `<table class="pro-wetting-table">${head}<tbody>${body}</tbody></table>`;
}

/** 슬라이드 3 KPI와 겹치지 않는 보조 메모만 */
function propsNotesBullets(result, max = 2) {
  const notes = Array.isArray(result?.props?.notes)
    ? result.props.notes.map((x) => String(x).trim()).filter(Boolean)
    : [];
  return listBullets(notes, max);
}

/** 슬라이드 3 KPI와 중복되지 않게: 온도 격자 표 + 기계 물성만 */
function wettingSlideContent(result) {
  const rows = getWettingByTempRows(result);
  const notes = propsNotesBullets(result, 2);
  const repTc = fmtMaybe(result?.props?.wetting_temp_c, 0);

  if (rows.length) {
    const blocks = [
      {
        type: "lead",
        text: `IDW 젖음 예측(측정 DB 250–290℃). Fmax·인장·전단 등 KPI는 「핵심 지표 · 조성」 슬라이드${repTc ? ` (대표 ${repTc}℃)` : ""}에 있습니다.`
      },
      { type: "html", html: renderWettingTableHtml(rows) }
    ];
    if (notes.length) blocks.push({ type: "bullets", items: notes });
    return { blocks, title: "젖음 온도 격자" };
  }

  if (!notes.length) return { blocks: [] };

  return {
    title: "물성 메모",
    blocks: [
      {
        type: "lead",
        text: "추가 물성 메모. 젖음·기계 KPI는 「핵심 지표 · 조성」 슬라이드를 참고하세요."
      },
      { type: "bullets", items: notes }
    ]
  };
}



function slideMeta(result, _melt, _profile) {

  const norm = getResultNorm(result);

  const keys = Object.keys(norm).filter((k) => Number(norm[k]) > 0);

  keys.sort((a, b) => (a === "Sn" ? -1 : b === "Sn" ? 1 : a.localeCompare(b)));

  const composition = keys.map((k) => `${k} ${fmtNum(norm[k], 2)}%`).join(" · ") || "—";

  // `melt.label` can be something like "하이브리드 엔진" which is confusing as a document title.
  // Keep the deck title stable; show melt basis elsewhere (metrics / inference / chart).
  const title = result?.best_name ? `${result.best_name} 분석 보고서` : "합금 분석 보고서";

  const date = new Date().toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });

  return { title, composition, date };

}



function escapeHtml(s) {

  return String(s)

    .replace(/&/g, "&amp;")

    .replace(/</g, "&lt;")

    .replace(/>/g, "&gt;")

    .replace(/"/g, "&quot;");

}



/** 블록 → HTML (슬라이드·오프라인 공용 클래스) */

export function renderBlocksHtml(blocks) {

  if (!Array.isArray(blocks) || !blocks.length) return "";

  return blocks

    .map((b) => {

      if (b.type === "lead") {

        return `<p class="pro-lead">${escapeHtml(b.text)}</p>`;

      }

      if (b.type === "bullets" && Array.isArray(b.items) && b.items.length) {

        const items = b.items.map((i) => `<li>${escapeHtml(i)}</li>`).join("");

        return `<ul class="pro-bullets">${items}</ul>`;

      }

      if (b.type === "html") return b.html || "";

      if (b.type === "kpi-row" && Array.isArray(b.items)) {

        const cells = b.items

          .map(

            (k) => `<div class="pro-kpi">

  <span class="pro-kpi__label">${escapeHtml(k.label)}</span>

  <span class="pro-kpi__value">${escapeHtml(k.value)}</span>

  ${k.hint ? `<span class="pro-kpi__hint">${escapeHtml(k.hint)}</span>` : ""}

</div>`

          )

          .join("");

        return `<div class="pro-kpi-grid">${cells}</div>`;

      }

      return "";

    })

    .join("\n");

}



function listBullets(items, max = 6) {

  if (!Array.isArray(items)) return [];

  const seen = new Set();
  const out = [];
  for (const x of items) {
    const v = String(x).trim();
    if (!v || seen.has(v)) continue;
    seen.add(v);
    out.push(v);
    if (out.length >= max) break;
  }
  return out;

}



function phaseSlideContent(result) {
  const phaseText = String(result?.phase || "").trim();
  const imc = listBullets(result?.imc, 6);
  const lead =
    summarizeLead(phaseText, 200) ||
    (imc.length ? "접합 계면 IMC 형성·성장 경향(공정 온도·시간에 민감)." : "");
  const bullets = imc.length ? imc : extractBullets(phaseText, 6);
  return { lead, bullets: listBullets(bullets, 6) };
}



function riskSlideContent(result) {

  const riskItems = listBullets(result?.risk, 6);

  const ai = String(result?.ai_summary || "").trim();

  return {

    // 기술 보고서 톤: AI 서술보다 “무엇을 검토해야 하는지”를 먼저 고정 문장으로 제시
    lead: riskItems.length ? "공정/신뢰성 관점에서 우선 검토가 필요한 리스크 항목입니다." : summarizeLead(ai),

    bullets: riskItems.length ? riskItems : extractBullets(ai, 5)

  };

}



function elementsSlideContent(result) {
  const norm = getResultNorm(result);
  const tech = [];
  const sn = Number(norm.Sn);
  const bi = Number(norm.Bi);
  const cu = Number(norm.Cu);
  const ag = Number(norm.Ag);
  if (sn > 0) tech.push(`Sn ${fmtNum(sn, 2)}%: 기지·유동·Θ 응답`);
  if (bi > 0) tech.push(`Bi ${fmtNum(bi, 2)}%: 저융·ΔT 축소${bi >= 15 ? " · ≥15% 취성·낙하 검토" : ""}`);
  if (ag > 0) tech.push(`Ag ${fmtNum(ag, 2)}%: 고용강화·Ag3Sn IMC`);
  if (cu > 0) tech.push(`Cu ${fmtNum(cu, 2)}%: Cu6Sn5 성장·EM${cu >= 0.7 ? " (≥0.7% 가속)" : ""}`);

  const dopant = String(result?.dopant_rec || "").trim();
  const roles = String(result?.element_roles || "").trim();
  const fallback = dopant ? extractBullets(dopant, 3) : extractBullets(roles, 4);
  const bullets = tech.length ? tech : fallback;

  return {
    lead: tech.length
      ? "wt% 기준 원소 기여·IMC·기계 특성 요약."
      : summarizeLead(roles) || summarizeLead(dopant) || "원소·첨가 변경 시 융점·IMC·신뢰성 영향 검토.",
    bullets: listBullets(bullets, 6)
  };
}



function inferenceSlideContent(result) {
  const inf = result?.alloy_inference;
  if (!inf || inf.solidus == null) return { lead: "", bullets: [] };

  const infS = Number(inf.solidus);
  const infL = Number(inf.liquidus);
  const infP = Number(inf.recommended_peak_c);
  const engS = Number(result?.solidus);
  const engL = Number(result?.liquidus);
  const engP = Number(result?.peak);

  const lead =
    Number.isFinite(engS) && Number.isFinite(engL)
      ? `핵심 하이브리드 엔진 계산값 — 고상 ${fmtNum(engS)} ℃ · 액상 ${fmtNum(engL)} ℃ · 계산 피크 ${fmtNum(engP)} ℃ · Δ ${fmtNum(engL - engS)} ℃`
      : "핵심 융점 계산은 하이브리드 엔진 값을 사용합니다.";

  const bullets = [];
  bullets.push(
    `교차확인 전용 — 유사 합금 DB 보간(3-NN 추론 모델): 고상 ${fmtNum(infS)} ℃ · 액상 ${fmtNum(infL)} ℃`
  );
  if (Number.isFinite(engS) && Number.isFinite(engL)) {
    const dS = infS - engS;
    const dL = infL - engL;
    const dP = infP - engP;
    const sign = (d) => (d >= 0 ? "+" : "");
    bullets.push(
      `엔진 대비 (보간 − 엔진): 고상 ${sign(dS)}${fmtNum(dS)} ℃ · 액상 ${sign(dL)}${fmtNum(dL)} ℃ · 피크 ${sign(dP)}${fmtNum(dP)} ℃`
    );
  }

  if (Array.isArray(inf.neighbors) && inf.neighbors.length) {
    const top = inf.neighbors.filter((n) => Number(n?.weight) > 0.001).slice(0, 3);
    if (top.length) {
      bullets.push(`유사 DB: ${top.map((n) => `${n.name || "?"}(w=${fmtNum(n.weight, 3)})`).join(" · ")}`);
    }
  }

  const report = String(inf.process_report || "").trim();
  const reportBullets = extractBullets(report, 5).filter((b) => !isMeltSummaryBullet(b));
  bullets.push(...reportBullets);

  return { lead, bullets: listBullets(bullets, 6) };
}



function isMeltSummaryBullet(text) {
  const t = String(text || "");
  return /(?:고상|액상|융점|solidus|liquidus)/i.test(t) && /\d+\s*℃/.test(t);
}

function summarySlideContent(result, meta) {

  const eng = stripReportDecor(result?.eng_report || result?.eng_summary);

  const engBullets = extractEngBullets(eng, 6).filter((b) => !isMeltSummaryBullet(b));
  const riskBullets = listBullets(result?.risk, 6);
  const imcBullets = listBullets(result?.imc, 6);

  const lead = techSummaryLead(result, meta);

  const bullets = [];
  bullets.push(...riskBullets.slice(0, 3));
  bullets.push(...imcBullets.slice(0, 3));
  if (bullets.length < 6) bullets.push(...engBullets);

  return { lead, bullets: listBullets(bullets, 6) };

}



function pushBriefSlide(slides, meta, id, title, content) {
  const blocks =
    content.blocks ||
    [
      ...(content.lead ? [{ type: "lead", text: content.lead }] : []),
      ...(content.bullets?.length ? [{ type: "bullets", items: content.bullets }] : [])
    ];
  if (!blocks.length) return;

  slides.push({
    id: `brief-${id}`,
    kind: "brief",
    title: content.title || title,
    subtitle: meta.composition,
    blocks
  });
}



/** 분석 결과 → 발표 슬라이드 덱 */

export function buildProfessionalReportSlides(payload) {

  const { result, profile, melt } = payload;

  const meta = slideMeta(result, melt, profile);

  const norm = getResultNorm(result);



  const processAllowed = result?.prediction_contract?.process_recommendation?.allowed !== false;

  const heroKpis = [

    { label: "고상선", value: `${fmtNum(result?.solidus)} ℃` },

    { label: "액상선", value: `${fmtNum(result?.liquidus)} ℃` },

    { label: "계산 피크", value: `${fmtNum(result?.peak)} ℃`, hint: "열역학 참고값" },

    {

      label: "종합 신뢰도",

      value: `${fmtNum(result?.confidence_overall, 0)} %`,

      hint: result?.best_name ? `DB: ${result.best_name}` : undefined

    }

  ];

  const propsKpis = buildPropsKpis(result);



  const compKeys = Object.keys(norm).filter((k) => Number(norm[k]) > 0);

  compKeys.sort((a, b) => (a === "Sn" ? -1 : b === "Sn" ? 1 : a.localeCompare(b)));

  const compCells = compKeys

    .map(

      (k) =>

        `<div class="pro-comp-cell"><span class="pro-comp-cell__el">${escapeHtml(k)}</span><span class="pro-comp-cell__pct">${fmtNum(norm[k], 2)}%</span></div>`

    )

    .join("");



  const summary = summarySlideContent(result, meta);

  const slides = [

    {

      id: "cover",

      kind: "cover",

      title: meta.title,

      subtitle: meta.composition,

      meta,

      heroKpis

    },

    {

      id: "executive",

      kind: "executive",

      title: "분석 요약",

      subtitle: meta.composition,

      blocks: [

        { type: "lead", text: summary.lead },

        {

          type: "bullets",

          items: summary.bullets.length

            ? summary.bullets

            : ["화면의 각 섹션(상분석·리스크·원소 역할)에서 상세 내용을 확인하세요."]

        }

      ]

    },

    {

      id: "metrics",

      kind: "metrics",

      title: "핵심 지표 · 조성",

      subtitle: meta.composition,

      heroKpis,

      blocks: [
        {

          type: "html",

          html: `<div class="pro-metrics-layout">

  <div class="pro-metrics-two">
    <div class="pro-comp-grid">${compCells || '<span class="pro-muted">조성 데이터 없음</span>'}</div>
    ${propsKpis.length ? `<div class="pro-metrics-kpis">${renderKpiCellsHtml(propsKpis.slice(0, 6))}</div>` : ""}
  </div>

  <div class="pro-callout">융점 창: ${fmtNum(result?.solidus)} – ${fmtNum(result?.liquidus)} ℃ · Δ ${fmtNum(Number(result?.liquidus) - Number(result?.solidus))} ℃</div>

</div>`

        }

      ]

    }

  ];



  pushBriefSlide(slides, meta, "phase", "상분석 · IMC", phaseSlideContent(result));

  pushBriefSlide(slides, meta, "risk", "신뢰성 리스크 · AI", riskSlideContent(result));

  pushBriefSlide(slides, meta, "wetting", "젖음 · 물성", wettingSlideContent(result));

  pushBriefSlide(slides, meta, "elements", "원소 역할 · 첨가", elementsSlideContent(result));

  pushBriefSlide(slides, meta, "inference", "데이터 추론 · 공정", inferenceSlideContent(result));



  const lab = String(result?.lab_report || "").trim();

  if (lab) {

    pushBriefSlide(slides, meta, "lab", "연구소 원문 요약", {

      lead: summarizeLead(lab),

      bullets: extractBullets(lab, 6)

    });

  }



  if (processAllowed) {
    slides.push({
      id: "charts",
      kind: "charts",
      title: "차트 요약",
      subtitle: "조성 분포 · 리플로우 프로파일"
    });
  } else {
    slides.push({
      id: "process-refused",
      kind: "brief",
      title: "공정 추천 중단",
      subtitle: meta.composition,
      blocks: [
        {
          type: "lead",
          text: "현재 조성은 DB 검증 범위 밖 또는 근거 부족으로 리플로우 차트와 피크 권장값을 보고서에 포함하지 않습니다."
        },
        {
          type: "bullets",
          items: ["DSC로 고상선·액상선을 확인하세요.", "부품 허용온도와 오븐 편차를 확인한 뒤 공학 검토를 다시 수행하세요."]
        }
      ]
    });
  }



  const meltRecap = `고상 ${fmtNum(result?.solidus)} – 액상 ${fmtNum(result?.liquidus)} ℃ · Δ ${fmtNum(Number(result?.liquidus) - Number(result?.solidus))} ℃ · 신뢰도 ${fmtNum(result?.confidence_overall, 0)}%`;

  slides.push({
    id: "closing",
    kind: "closing",
    title: result?.best_name || "Alloy Predictor",
    subtitle: meltRecap,
    meta
  });



  return slides;

}
