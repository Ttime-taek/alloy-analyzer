import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  analysisReportMeta,
  buildReportSlides,
  buildStandaloneAnalysisHtml,
  compositionChartData,
  reflowChartData
} from "./analysisChartReport.js";
import { useChartInstance } from "./useChartInstance.js";

const chartGrid = { color: "#334155" };
const chartTicks = { color: "#94a3b8", font: { size: 11 } };

function buildCompositionConfig(norm) {
  const { labels, values } = compositionChartData(norm);
  if (!labels.length) return null;
  return {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "wt%",
          data: values,
          backgroundColor: ["#38bdf8", "#34d399", "#a78bfa", "#fbbf24", "#f87171", "#fb923c", "#94a3b8"],
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: chartTicks, grid: { display: false } },
        y: { ticks: chartTicks, grid: chartGrid }
      }
    }
  };
}

function buildReflowConfig(profile) {
  const { labels, values } = reflowChartData(profile);
  if (!labels.length) return null;
  return {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "℃",
          data: values,
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.12)",
          fill: true,
          tension: 0.25,
          pointRadius: 0
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { ...chartTicks, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
          grid: chartGrid
        },
        y: { ticks: chartTicks, grid: chartGrid }
      }
    }
  };
}

function KpiStrip({ items, variant = "default" }) {
  if (!items?.length) return null;
  return (
    <div className={`rs-kpi-strip rs-kpi-strip--${variant}`}>
      {items.map((k) => (
        <div className="rs-kpi" key={k.label}>
          <span className="rs-kpi__label">{k.label}</span>
          <span className="rs-kpi__value">{k.value}</span>
          {k.hint ? <span className="rs-kpi__hint">{k.hint}</span> : null}
        </div>
      ))}
    </div>
  );
}

function SlideProse({ blocks }) {
  if (!blocks?.length) return null;
  return (
    <div className="rs-prose">
      {blocks.map((b, i) => {
        if (b.type === "lead") {
          return (
            <p key={`lead-${i}`} className="rs-lead">
              {b.text}
            </p>
          );
        }
        if (b.type === "bullets" && Array.isArray(b.items) && b.items.length) {
          return (
            <ul key={`bullets-${i}`} className="rs-bullets">
              {b.items.map((item, j) => (
                <li key={j}>{item}</li>
              ))}
            </ul>
          );
        }
        if (b.type === "html") {
          return <div key={`html-${i}`} className="rs-html-block" dangerouslySetInnerHTML={{ __html: b.html }} />;
        }
        return null;
      })}
    </div>
  );
}

function SlideCharts({ norm, profile }) {
  const compConfig = useMemo(() => buildCompositionConfig(norm), [norm]);
  const reflowConfig = useMemo(() => buildReflowConfig(profile), [profile]);
  const compRef = useChartInstance(compConfig, [compConfig]);
  const reflowRef = useChartInstance(reflowConfig, [reflowConfig]);
  return (
    <div className="rs-charts">
      <div className="rs-chart-panel">
        <span className="rs-chart-label">조성 (wt%)</span>
        <div className="rs-chart-canvas-wrap">
          {compConfig ? <canvas ref={compRef} /> : <p className="rs-muted">조성 데이터 없음</p>}
        </div>
      </div>
      <div className="rs-chart-panel">
        <span className="rs-chart-label">리플로우 프로파일</span>
        <div className="rs-chart-canvas-wrap">
          {reflowConfig ? <canvas ref={reflowRef} /> : <p className="rs-muted">리플로우 프로파일 없음</p>}
        </div>
      </div>
    </div>
  );
}

function SlideChrome({ index, total, eyebrow, title, subtitle, onClose, onSaveHtml }) {
  return (
    <header className="rs-chrome">
      <div className="rs-chrome__titles">
        {eyebrow ? <p className="rs-chrome__eyebrow">{eyebrow}</p> : null}
        <h2 className="rs-chrome__title">{title}</h2>
        {subtitle ? <p className="rs-chrome__subtitle">{subtitle}</p> : null}
      </div>
      <div className="rs-chrome__actions">
        <span className="rs-chrome__page">
          {index + 1} / {total}
        </span>
        <button type="button" className="rs-btn rs-btn--save" onClick={onSaveHtml}>
          HTML 저장
        </button>
        <button type="button" className="rs-btn rs-btn--close" onClick={onClose}>
          닫기 ✕
        </button>
      </div>
    </header>
  );
}

function SlideBody({ slide, norm, profile }) {
  if (slide.kind === "cover") {
    return (
      <div className="rs-body rs-body--cover">
        <p className="rs-cover-tag">Technical Analysis Report</p>
        <h1 className="rs-cover-title">{slide.title}</h1>
        <p className="rs-cover-sub">{slide.subtitle}</p>
        <KpiStrip items={slide.heroKpis} variant="cover" />
        <p className="rs-cover-date">{slide.meta?.date}</p>
      </div>
    );
  }
  if (slide.kind === "closing") {
    return (
      <div className="rs-body rs-body--closing">
        <h2 className="rs-closing-title">{slide.title}</h2>
        <p className="rs-closing-sub">{slide.subtitle}</p>
        <p className="rs-cover-date">{slide.meta?.date}</p>
      </div>
    );
  }
  if (slide.kind === "charts") {
    return (
      <div className="rs-body rs-body--charts">
        <SlideCharts norm={norm} profile={profile} />
      </div>
    );
  }

  return (
    <div className={`rs-body rs-body--content rs-body--${slide.kind}`}>
      {slide.heroKpis?.length ? <KpiStrip items={slide.heroKpis} /> : null}
      <SlideProse blocks={slide.blocks} />
    </div>
  );
}

export default function AnalysisReportSlideshow({ open, onClose, payload }) {
  const [index, setIndex] = useState(0);
  const [wettingRows, setWettingRows] = useState(null);

  useEffect(() => {
    if (!open || !payload?.result?.norm) {
      setWettingRows(null);
      return undefined;
    }
    const existing = payload.result.props?.wetting_by_temp;
    if (Array.isArray(existing) && existing.length) {
      setWettingRows(existing);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/wetting_grid", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comp: payload.result.norm })
        });
        const data = await res.json().catch(() => ({}));
        if (!cancelled) {
          setWettingRows(res.ok && Array.isArray(data.wetting_by_temp) ? data.wetting_by_temp : []);
        }
      } catch {
        if (!cancelled) setWettingRows([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, payload?.result?.norm, payload?.result?.props?.wetting_by_temp]);

  const deckPayload = useMemo(() => {
    if (!payload?.result) return payload;
    const existing = payload.result.props?.wetting_by_temp;
    if (Array.isArray(existing) && existing.length) return payload;
    if (!Array.isArray(wettingRows) || !wettingRows.length) return payload;
    return {
      ...payload,
      result: {
        ...payload.result,
        props: { ...(payload.result.props || {}), wetting_by_temp: wettingRows }
      }
    };
  }, [payload, wettingRows]);

  const slides = useMemo(() => (deckPayload?.result ? buildReportSlides(deckPayload) : []), [deckPayload]);
  const norm =
    payload?.result?.norm ||
    payload?.result?.composition_normalized ||
    payload?.result?.composition ||
    {};
  const meta = useMemo(
    () => (payload?.result ? analysisReportMeta(payload.result, payload.melt, payload.profile) : null),
    [payload]
  );
  const total = slides.length;

  useEffect(() => {
    if (open) setIndex(0);
  }, [open, payload?.result]);

  useEffect(() => {
    if (!open || !total) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open, total]);

  const go = useCallback(
    (delta) => {
      setIndex((i) => {
        if (!total) return 0;
        return (i + delta + total) % total;
      });
    },
    [total]
  );

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
      if (e.key === "ArrowLeft") go(-1);
      if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, go]);

  const downloadHtml = useCallback(() => {
    if (!payload?.result) return;
    const html = buildStandaloneAnalysisHtml(deckPayload);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `alloy-report-${Date.now()}.html`;
    a.click();
    URL.revokeObjectURL(a.href);
  }, [deckPayload]);

  if (!open || !total || !meta) return null;

  const slide = slides[index];
  const progress = ((index + 1) / total) * 100;
  const chromeTitle =
    slide.kind === "cover" ? slide.title : slide.title;
  const chromeSub =
    slide.kind === "cover" ? slide.subtitle : slide.subtitle || meta.composition;
  const chromeEyebrow =
    slide.kind === "cover"
      ? "Technical Analysis Report"
      : slide.kind === "closing"
        ? "보고서 종료"
        : slide.kind === "charts"
          ? "차트"
          : slide.kind === "executive"
            ? "분석 요약"
            : slide.kind === "metrics"
              ? "핵심 지표"
              : slide.title || "분석 보고서";

  return createPortal(
    <div className="report-slideshow" role="dialog" aria-modal="true" aria-label="슬라이드 보고서">
      <div className="report-slideshow__backdrop" aria-hidden />
      <div className="report-slideshow__frame">
        <article className="rs-deck">
          <SlideChrome
            index={index}
            total={total}
            eyebrow={chromeEyebrow}
            title={chromeTitle === "합금 분석 보고서" ? "분석 결과" : chromeTitle}
            subtitle={chromeSub}
            onClose={onClose}
            onSaveHtml={downloadHtml}
          />
          <div className="rs-deck__main">
            <button
              type="button"
              className="rs-deck__nav rs-deck__nav--prev"
              onClick={() => go(-1)}
              aria-label="이전 슬라이드"
            >
              ‹
            </button>
            <div className="rs-deck__slide" key={index}>
              <SlideBody slide={slide} norm={norm} profile={deckPayload.profile} />
            </div>
            <button
              type="button"
              className="rs-deck__nav rs-deck__nav--next"
              onClick={() => go(1)}
              aria-label="다음 슬라이드"
            >
              ›
            </button>
          </div>
          <div className="rs-deck__footer">
            <div className="rs-deck__progress" aria-hidden>
              <div className="rs-deck__progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <div className="rs-deck__dots" role="tablist">
              {slides.map((s, i) => (
                <button
                  key={s.id}
                  type="button"
                  role="tab"
                  aria-selected={i === index}
                  aria-label={`${i + 1}. ${s.title}`}
                  className={`rs-deck__dot${i === index ? " is-active" : ""}`}
                  onClick={() => setIndex(i)}
                />
              ))}
            </div>
            <p className="rs-deck__hint">← → 이동 · Esc 닫기</p>
          </div>
        </article>
      </div>
    </div>,
    document.body
  );
}
