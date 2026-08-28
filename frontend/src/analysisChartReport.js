/**
 * Chart.js용 분석 결과 데이터·독립 HTML(접이식 전체 보고서) 생성
 */
import {
  buildProfessionalReportSlides,
  getResultNorm,
  renderBlocksHtml
} from "./professionalReportSlides.js";

export { buildProfessionalReportSlides as buildReportSlides } from "./professionalReportSlides.js";

function fmtNum(v, digits = 1) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** 조성 막대 차트 */
export function compositionChartData(norm) {
  const comp = norm && typeof norm === "object" ? norm : {};
  const entries = Object.entries(comp)
    .filter(([, v]) => Number(v) > 0)
    .sort((a, b) => {
      if (a[0] === "Sn") return -1;
      if (b[0] === "Sn") return 1;
      return b[1] - a[1];
    });
  return {
    labels: entries.map(([k]) => k),
    values: entries.map(([, v]) => Number(v))
  };
}

/** 리플로우 라인 차트 */
function formatReflowTimeLabel(p) {
  const t = Number(p.t ?? p.time ?? 0);
  if (!Number.isFinite(t)) return "0s";
  const rounded = Math.round(t);
  if (Math.abs(t - rounded) < 0.05) return `${rounded}s`;
  return `${t.toFixed(1)}s`;
}

export function reflowChartData(profile) {
  const pts = Array.isArray(profile?.points) ? profile.points : [];
  return {
    labels: pts.map((p) => formatReflowTimeLabel(p)),
    // App.jsx `buildPeakProfilePoints()` uses {t, y}. Older/alt shapes may use temp/temperature.
    values: pts.map((p) => Number(p.y ?? p.temp ?? p.temperature ?? 0))
  };
}

export function analysisReportMeta(result, melt, profile) {
  const norm = getResultNorm(result);
  const keys = Object.keys(norm).filter((k) => Number(norm[k]) > 0);
  keys.sort((a, b) => (a === "Sn" ? -1 : b === "Sn" ? 1 : a.localeCompare(b)));
  const composition = keys.map((k) => `${k} ${fmtNum(norm[k], 2)}%`).join(" · ") || "—";
  const title = melt?.label || profile?.meta?.presetName || result?.best_name || "합금 분석 보고서";
  const date = new Date().toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
  return { title, composition, date };
}

/** 접이식 HTML 섹션 수집 */
export function collectReportSections(payload) {
  const { result } = payload;
  if (!result) return [];
  const sections = [];
  const push = (id, title, body) => {
    if (!body) return;
    sections.push({ id, title, bodyHtml: body });
  };

  if (result.phase) {
    push("phase", "상분석 / IMC", `<pre class="report-pre">${escapeHtml(result.phase)}</pre>`);
  }
  if (Array.isArray(result.imc) && result.imc.length) {
    push("imc", "예상 IMC", `<pre class="report-pre">${escapeHtml(result.imc.join("\n"))}</pre>`);
  }
  if (Array.isArray(result.risk) && result.risk.length) {
    push("risk", "신뢰성 리스크", `<pre class="report-pre">${escapeHtml(result.risk.join("\n"))}</pre>`);
  }
  if (result.ai_summary) {
    push("ai", "AI 요약", `<pre class="report-pre">${escapeHtml(result.ai_summary)}</pre>`);
  }
  if (result.eng_report) push("eng", "쉬운 요약", `<pre class="report-pre">${escapeHtml(result.eng_report)}</pre>`);
  if (result.lab_report) push("lab", "연구소 원문", `<pre class="report-pre">${escapeHtml(result.lab_report)}</pre>`);
  return sections;
}

export function buildReportSectionsHtml(sections) {
  if (!sections?.length) return "";
  return sections
    .map(
      (s) => `<details class="report-details" open>
  <summary>${escapeHtml(s.title)}</summary>
  <div class="report-details__body">${s.bodyHtml}</div>
</details>`
    )
    .join("\n");
}

/** 슬라이드·인라인 공용 CSS (index.css .pro-* / .report-slideshow-* 와 동기화) */
export const REPORT_SLIDE_CSS = `
:root {
  --slide-pad-x: 40px;
  --slide-pad-y: 28px;
  --slide-title: clamp(22px, 2.2vw, 28px);
  --slide-body: 15px;
  --slide-lead: clamp(16px, 1.45vw, 18px);
}
.pro-lead {
  margin: 0;
  font-size: var(--slide-lead);
  line-height: 1.65;
  color: #e2e8f0;
  padding: 0 0 0 16px;
  border-left: 3px solid #60a5fa;
  max-width: 56em;
}
.pro-bullets {
  margin: 0;
  padding-left: 1.25em;
  list-style: disc;
}
.pro-bullets li {
  display: list-item;
  margin-bottom: 8px;
  font-size: var(--slide-body);
  line-height: 1.62;
  color: #cbd5e1;
}
.pro-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
/* 밀도 높은 보고서: 물성 KPI는 3열(최대 2줄)로 고정 */
.pro-metrics-kpis .pro-kpi-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.pro-metrics-kpis .pro-kpi__value { font-size: clamp(16px, 1.6vw, 20px); }
.pro-metrics-kpis .pro-kpi__hint { font-size: 10px; line-height: 1.3; }
@media (max-width: 880px) {
  .pro-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .pro-metrics-kpis .pro-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.pro-kpi {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-height: 84px;
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.55);
  border: 1px solid rgba(51, 65, 85, 0.65);
}
.pro-kpi__label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #94a3b8;
  line-height: 1.3;
}
.pro-kpi__value {
  font-size: clamp(20px, 2vw, 26px);
  font-weight: 800;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  color: #f8fafc;
}
.pro-kpi__hint {
  font-size: 11px;
  line-height: 1.35;
  color: #7b8794;
  overflow-wrap: anywhere;
}
.pro-metrics-layout {
  display: grid;
  grid-template-rows: 1fr auto;
  gap: 16px;
  flex: 1;
  min-height: 0;
}
.pro-comp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 10px;
  align-content: start;
}
.pro-comp-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 72px;
  padding: 10px 8px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid rgba(51, 65, 85, 0.5);
}
.pro-comp-cell__el {
  font-size: 13px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.04em;
}
.pro-comp-cell__pct {
  font-size: 17px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: #f1f5f9;
}
.pro-callout {
  font-size: 14px;
  line-height: 1.5;
  padding: 12px 16px;
  border-radius: 8px;
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: #bae6fd;
}
.pro-wetting-table {
  width: 100%;
  max-width: 520px;
  border-collapse: collapse;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.pro-wetting-table th,
.pro-wetting-table td {
  padding: 10px 14px;
  text-align: right;
  border-bottom: 1px solid rgba(51, 65, 85, 0.65);
}
.pro-wetting-table th:first-child,
.pro-wetting-table td:first-child { text-align: left; }
.pro-wetting-table th {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #94a3b8;
}
.pro-wetting-table td { color: #e2e8f0; }
.pro-muted { color: #7b8794; font-size: 14px; }
.slide-body--executive {
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1;
  min-height: 0;
}
.slide-body--metrics {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
}
`;

export function buildStandaloneAnalysisHtml(payload) {
  const slides = buildProfessionalReportSlides(payload);
  const meta = analysisReportMeta(payload.result, payload.melt, payload.profile);
  const sections = collectReportSections(payload);
  const detailsHtml = buildReportSectionsHtml(sections);

  const slideHtml = slides
    .map((slide, i) => {
      let body = "";
      if (slide.kind === "cover") {
        const kpis = renderBlocksHtml([{ type: "kpi-row", items: slide.heroKpis || [] }]);
        body = `<div class="slide-cover">
  <p class="slide-cover__doctype">Technical Analysis Report</p>
  <h1 class="slide-cover__title">${escapeHtml(slide.title)}</h1>
  <p class="slide-cover__sub">${escapeHtml(slide.subtitle)}</p>
  ${kpis}
  <p class="slide-cover__date">${escapeHtml(meta.date)}</p>
</div>`;
      } else if (slide.kind === "closing") {
        body = `<div class="slide-closing">
  <h2 class="slide-closing__title">${escapeHtml(slide.title)}</h2>
  <p class="slide-closing__sub">${escapeHtml(slide.subtitle)}</p>
  <p class="slide-closing__date">${escapeHtml(meta.date)}</p>
</div>`;
      } else if (slide.kind === "charts") {
        body = `<div class="slide-charts-grid">
  <div class="slide-chart-panel"><canvas id="chart-comp-${i}"></canvas></div>
  <div class="slide-chart-panel"><canvas id="chart-reflow-${i}"></canvas></div>
</div>`;
      } else {
        const bodyClass =
          slide.kind === "executive"
            ? "slide-body--executive"
            : slide.kind === "metrics"
              ? "slide-body--metrics"
              : "slide-body--brief";
        body = `<div class="${bodyClass}">${renderBlocksHtml(slide.blocks || [])}</div>`;
        if (slide.heroKpis?.length) {
          body = `${renderBlocksHtml([{ type: "kpi-row", items: slide.heroKpis }])}${body}`;
        }
      }
      return `<section class="slide" data-index="${i}">
  <header class="slide-head">
    <span class="slide-head__index">${String(i + 1).padStart(2, "0")}</span>
    <h2 class="slide-head__title">${escapeHtml(slide.title)}</h2>
    ${slide.subtitle ? `<p class="slide-head__subtitle">${escapeHtml(slide.subtitle)}</p>` : ""}
  </header>
  <div class="slide-body">${body}</div>
</section>`;
    })
    .join("\n");

  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>${escapeHtml(meta.title)} — 분석 보고서</title>
<style>
${REPORT_SLIDE_CSS}
body { margin: 0; font-family: "Pretendard", system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
.deck { min-height: 100dvh; display: flex; flex-direction: column; }
.deck-main { flex: 1; display: flex; flex-direction: column; padding: 16px; }
.slide { display: none; flex: 1; flex-direction: column; min-height: 0; background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; }
.slide.is-active { display: flex; }
.slide-head {
  flex-shrink: 0;
  padding: 20px var(--slide-pad-x) 12px;
  border-bottom: 1px solid #334155;
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 16px;
  row-gap: 4px;
  align-items: baseline;
}
.slide-head__index { grid-row: 1 / -1; align-self: center; font-size: 11px; font-weight: 600; letter-spacing: 0.12em; color: #7b8794; }
.slide-head__title { margin: 0; font-size: var(--slide-title); font-weight: 800; line-height: 1.2; letter-spacing: -0.02em; grid-column: 2; }
.slide-head__subtitle { margin: 0; grid-column: 2; font-size: 13px; color: #94a3b8; line-height: 1.45; overflow-wrap: anywhere; }
.slide-body { flex: 1; min-height: 0; padding: var(--slide-pad-y) var(--slide-pad-x); display: flex; flex-direction: column; overflow: hidden; }
.slide-cover, .slide-closing { flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; gap: 16px; padding: 24px; }
.slide-cover__doctype { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: #7b8794; margin: 0; }
.slide-cover__title { font-size: clamp(28px, 4vw, 40px); font-weight: 800; margin: 0; line-height: 1.15; max-width: 18ch; }
.slide-cover__sub { font-size: 15px; color: #94a3b8; margin: 0; max-width: 42em; line-height: 1.5; overflow-wrap: anywhere; }
.slide-cover__date, .slide-closing__date { font-size: 13px; color: #7b8794; margin: 8px 0 0; }
.slide-cover .pro-kpi-grid { width: 100%; max-width: 720px; margin-top: 8px; }
.slide-charts-grid { flex: 1; display: grid; grid-template-columns: 0.95fr 1.45fr; gap: 20px; min-height: 280px; }
.slide-chart-panel { min-height: 0; padding: 12px; border-radius: 10px; background: rgba(15,23,42,0.5); border: 1px solid #334155; position: relative; }
.slide-chart-panel canvas { width: 100% !important; height: 100% !important; }
.report-details { margin: 16px; border: 1px solid #334155; border-radius: 8px; }
.report-pre { white-space: pre-wrap; font-size: 13px; line-height: 1.55; margin: 0; padding: 12px; }
.nav { display: flex; gap: 8px; justify-content: center; padding: 12px; }
.nav button { padding: 8px 16px; border-radius: 8px; border: 1px solid #475569; background: #1e293b; color: #e2e8f0; cursor: pointer; }
</style>
</head>
<body>
<div class="deck">
<div class="deck-main">${slideHtml}</div>
<nav class="nav">
<button type="button" id="prev">‹ 이전</button>
<button type="button" id="next">다음 ›</button>
</nav>
${detailsHtml ? `<div class="report-appendix">${detailsHtml}</div>` : ""}
</div>
<script>
(function(){
  var slides = document.querySelectorAll('.slide');
  var idx = 0;
  function show(i) {
    idx = (i + slides.length) % slides.length;
    slides.forEach(function(s, j) { s.classList.toggle('is-active', j === idx); });
  }
  document.getElementById('prev').onclick = function() { show(idx - 1); };
  document.getElementById('next').onclick = function() { show(idx + 1); };
  document.onkeydown = function(e) {
    if (e.key === 'ArrowLeft') show(idx - 1);
    if (e.key === 'ArrowRight') show(idx + 1);
  };
  show(0);
})();
</script>
</body>
</html>`;
}
