export const BASELINE_ALLOY = Object.freeze({
  name: "Sn1Ag25Bi0.7Cu",
  solidusC: 137.81
});

export function buildSummaryStripModel(result, baseline = BASELINE_ALLOY) {
  if (!result) return null;
  const solidus = Number(result.solidus);
  if (!Number.isFinite(solidus)) return null;

  const baselineSolidus = Number(baseline?.solidusC);
  const baselineName = String(baseline?.name || "").trim() || "baseline";
  if (!Number.isFinite(baselineSolidus)) return null;

  return {
    solidusC: solidus,
    baseline: { name: baselineName, solidusC: baselineSolidus }
  };
}

