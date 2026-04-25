export const BASELINE_ALLOY = Object.freeze({
  name: "Sn1Ag25Bi0.7Cu",
  solidusC: 137.81
});

export function formatSignedTempDeltaC(deltaC) {
  const d = Number(deltaC);
  if (!Number.isFinite(d)) return null;
  const v = Math.abs(d).toFixed(1);
  if (d > 0) return `+${v}℃`;
  if (d < 0) return `-${v}℃`;
  return `0.0℃`;
}

export function buildSummaryStripModel(result, baseline = BASELINE_ALLOY) {
  if (!result) return null;
  const solidus = Number(result.solidus);
  if (!Number.isFinite(solidus)) return null;

  const baselineSolidus = Number(baseline?.solidusC);
  const baselineName = String(baseline?.name || "").trim() || "baseline";
  if (!Number.isFinite(baselineSolidus)) return null;

  const deltaSolidus = solidus - baselineSolidus;
  return {
    solidusC: solidus,
    baseline: { name: baselineName, solidusC: baselineSolidus },
    deltaSolidusC: deltaSolidus,
    deltaSolidusText: formatSignedTempDeltaC(deltaSolidus)
  };
}

