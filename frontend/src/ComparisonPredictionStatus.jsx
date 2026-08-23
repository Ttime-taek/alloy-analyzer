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

function ContractCard({ side, contract }) {
  if (!contract || typeof contract !== "object") return null;
  const color = STATE_COLOR[contract.overall_state] || "#94a3b8";
  const properties = Object.entries(contract.properties || {});
  const refused = contract.overall_usage === "refused";
  const reasons = properties
    .flatMap(([, value]) => value?.reason_labels_ko || [])
    .filter(Boolean);
  const reason = [...new Set(reasons)][0];

  return (
    <div
      className="compare-contract-card"
      data-state={contract.overall_state || "unavailable"}
      style={{ borderColor: `${color}88`, background: `${color}12` }}
    >
      <div className="compare-contract-card__head">
        <strong style={{ color }}>{side}</strong>
        <span>{contract.family || "합금"} · {contract.overall_state_label_ko || "판정 없음"}</span>
        <b style={{ color }}>{contract.overall_usage_label_ko || "확인 필요"}</b>
      </div>
      <div className="compare-contract-card__properties">
        {properties.map(([name, value]) => (
          <span key={name} style={{ color: STATE_COLOR[value?.state] || "#94a3b8" }}>
            {PROPERTY_LABEL[name] || name} {value?.state_label_ko || "판정 없음"}
          </span>
        ))}
      </div>
      {refused ? (
        <div className="compare-contract-card__warning">
          이 조성의 예측값은 비교 참고용으로도 사용을 중단하세요.
          {reason ? ` ${reason}` : ""}
        </div>
      ) : null}
    </div>
  );
}

export default function ComparisonPredictionStatus({ a, b }) {
  const contractA = a?.prediction_contract;
  const contractB = b?.prediction_contract;
  if (!contractA && !contractB) return null;
  const refused = [contractA, contractB].some((contract) => contract?.overall_usage === "refused");

  return (
    <section
      className="compare-contract-status"
      aria-label="융점·인장 비교 예측 사용 판정"
      role={refused ? "alert" : undefined}
    >
      <div className="compare-contract-status__title">
        융점·인장 비교 예측 사용 판정
        <span>DB 근접 신뢰도와 실제 사용 가능 판정은 다릅니다. 전단·젖음은 이 판정에서 제외됩니다.</span>
      </div>
      <div className="compare-contract-status__grid">
        <ContractCard side="A" contract={contractA} />
        <ContractCard side="B" contract={contractB} />
      </div>
      <div className="compare-contract-card__warning">
        전단·젖음·인장 값은 각 항목에 표시된 원출처와 검증 상태가 일치할 때만 B−A·우열·추천에 사용합니다.
      </div>
    </section>
  );
}
