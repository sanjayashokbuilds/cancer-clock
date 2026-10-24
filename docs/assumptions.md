# Assumptions and limits

- Release timing: 14th of observation month + 2, with unverified historical
  vintages and latest revised values. Exact source upload dates are separate.
- The fixed cohort has 133 NHS trusts with observations in the evaluation era.
  No historical merger crosswalk is inferred. Missing recent history yields an
  unavailable forecast, not a fabricated continuation.
- First outpatient attendances are a volume proxy, not incoming referrals.
  DM01 includes non-cancer demand. Aggregate associations are not causal.
- Early training permits a partial 26-week window (minimum nine observed weeks).
  Paired evaluation retains all original Stage 2 eligibility requirements.
- Interval warm-up borrows baseline widths. Later calibration uses issued errors
  with published outcomes; dependence prevents a formal coverage guarantee.
- Strike dates are sourced and used only as past calendar indicators. Time-of-day
  boundaries are approximated to days; no strike capacity loss is inferred.
  The future simulator's 0.952 factor remains an unverified editable assumption.
- Probability calibration failed to improve Brier in this run. Scores are shown
  alongside simple benchmarks; probabilities are experimental.
- No personal waits, lives-saved estimates or causal recovery recommendations.
- Stage 4 uses a fixed 50:50 blend after retrospective review, not independent
  model selection. Trust-cluster bootstrap does not model shared national shocks.
- Large-swings cases depend on future actuals and cannot be selected at issue.
- Only 4-week qualitative growth signals are exported; thresholds 0.4/0.6 and
  agreement with the count forecast are assumed, not calibrated confidence.
- Bottleneck gaps, volume floors, shrinkage and confidence rules are screening
  assumptions. DM01 contains non-cancer demand and repeated monthly patients.
  FDS discordance and insufficient evidence are explicit. National DTT context
  is never copied into trust-level splits. See `bottleneck_method.md`.
