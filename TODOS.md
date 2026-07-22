# Deferred follow-up work

## Prediction quality

- Re-train or replace prediction models only if the grouped holdout report fails the agreed property thresholds.
- Compare the calibrated predictions with an independent CALPHAD/thermodynamic reference set.
- Add measured-condition metadata and source identifiers to every legacy DB row.
- Build a feedback loop that imports verified DSC/tensile measurements and re-runs calibration.

## Product expansion

- Add target-property inverse design with constrained candidate generation and Pareto comparison.
- Replace the single fixed baseline alloy with a user goal or automatically selected comparable alloy.
- Add experiment-priority recommendations based on uncertainty reduction.

## Platform

- Add organization accounts, per-organization quotas, audit retention, and private composition storage if the public tool becomes multi-tenant.
- Move AI idempotency/rate limiting to shared storage if the API is deployed with multiple instances.
- Add laboratory equipment integrations after the measurement data contract is stable.
