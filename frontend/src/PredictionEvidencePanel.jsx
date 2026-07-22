import React from "react";

const STATE_COLOR = {
  exact_match: "#22c55e",
  in_domain: "#38bdf8",
  weak_support: "#f59e0b",
  out_of_domain: "#fb7185",
  unavailable: "#94a3b8",
  data_quality_error: "#ef4444"
};

const PROPERTY_LABEL = {
  solidus_c: "고상선",
  liquidus_c: "액상선",
  tensile_strength_mpa: "인장강도"
};

function formatNumber(value, digits = 1) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "N/A";
}

function PropertyEvidence({ name, value }) {
  if (!value) return null;
  const interval = value.interval;
  const color = STATE_COLOR[value.state] || "#94a3b8";
  const range =
    interval && Number(interval.lower) !== Number(interval.upper)
      ? `${formatNumber(interval.lower)}–${formatNumber(interval.upper)} ${value.unit}`
      : value.state === "exact_match"
        ? "등록 DB 값"
        : "오차범위 없음";
  return (
    <div
      style={{
        padding: "10px 11px",
        borderRadius: 8,
        border: "1px solid #334155",
        background: "rgba(15,23,42,0.72)"
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 700 }}>
          {PROPERTY_LABEL[name] || name}
        </span>
        <span style={{ fontSize: 11, color, fontWeight: 700 }}>{value.state_label_ko}</span>
      </div>
      <div style={{ marginTop: 3, fontSize: 18, color: "#f8fafc", fontWeight: 800 }}>
        {formatNumber(value.point)} {value.unit}
      </div>
      <div style={{ marginTop: 3, fontSize: 11, color: "#cbd5e1" }}>경험적 90% 범위: {range}</div>
      <div style={{ marginTop: 3, fontSize: 10, color: "#64748b" }}>
        최근접 거리 {formatNumber(value.evidence?.nearest_distance, 3)} · {value.usage_label_ko}
      </div>
    </div>
  );
}

export default function PredictionEvidencePanel({ contract }) {
  if (!contract || typeof contract !== "object") return null;
  const properties = contract.properties || {};
  const process = contract.process_recommendation || {};
  const stateColor = STATE_COLOR[contract.overall_state] || "#94a3b8";
  return (
    <section
      aria-label="예측 근거와 사용 가능 범위"
      data-testid="prediction-evidence-panel"
      style={{
        marginBottom: 12,
        padding: 12,
        borderRadius: 10,
        border: `1px solid ${stateColor}66`,
        background: "linear-gradient(180deg, rgba(15,23,42,0.92), rgba(2,6,23,0.9))"
      }}
    >
      <div style={{ display: "flex", gap: 8, justifyContent: "space-between", flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 12, color: "#94a3b8", fontWeight: 700 }}>전체 물성 예측 판정</div>
          <div style={{ marginTop: 2, color: "#f8fafc", fontSize: 16, fontWeight: 800 }}>
            {contract.family} · {contract.overall_state_label_ko}
          </div>
        </div>
        <span
          style={{
            alignSelf: "flex-start",
            padding: "5px 9px",
            borderRadius: 999,
            background: `${stateColor}22`,
            border: `1px solid ${stateColor}88`,
            color: stateColor,
            fontSize: 11,
            fontWeight: 800
          }}
        >
          {contract.overall_usage_label_ko}
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 170px), 1fr))",
          gap: 8,
          marginTop: 10
        }}
      >
        {Object.entries(properties).map(([name, value]) => (
          <PropertyEvidence key={name} name={name} value={value} />
        ))}
      </div>

      <div
        style={{
          marginTop: 10,
          padding: "9px 10px",
          borderRadius: 8,
          background: process.allowed ? "rgba(14,116,144,0.16)" : "rgba(127,29,29,0.2)",
          border: process.allowed ? "1px solid #0e7490" : "1px solid #991b1b",
          color: "#e2e8f0",
          fontSize: 11,
          lineHeight: 1.5
        }}
      >
        <strong>리플로우 사용 판정: {process.usage_label_ko || "확인 필요"}</strong>
        {process.recommended_peak_c != null ? (
          <span> · 기준 피크 {formatNumber(process.recommended_peak_c)} ℃</span>
        ) : null}
        {Array.isArray(process.reason_labels_ko) && process.reason_labels_ko.length ? (
          <div style={{ marginTop: 3, color: "#cbd5e1" }}>{process.reason_labels_ko.join(" ")}</div>
        ) : null}
      </div>
      <div style={{ marginTop: 7, fontSize: 10, color: "#64748b", lineHeight: 1.45 }}>
        {contract.disclaimer_ko}
      </div>
    </section>
  );
}
