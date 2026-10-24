# Stage 2 methodology

Target: observed weekly count still waiting beyond 62 days, not total waiting
list size. Fixed cohort: 133 NHS trusts with observations in the evaluation era.
No merger stitching. Missing weeks remain missing; retired codes are not extrapolated.

Origins: every 28 days from Sunday 7 January 2024 through available 2026 history.
Training may use April–September 2023; scoring never uses pre-October outcomes.
Each origin filters `published_on <= issue` before building features, scales or
calibration errors. All releases use M+2/day14. **Approximate: latest revised
values**; this is not a reconstructed historical-vintage backtest.

For last observation t and issue a: observation-anchored target = t+h and true
lead = t+h-a. Issue-anchored target = a+h and extrapolation = a+h-t. Both are
reported at 4/8/12 weeks. Future-only observation scores are separate from all
scores; the latter can contain retrospective estimation of unpublished outcomes.

Persistence = last value. Drift = last + horizon × (last − value 8 weeks ago)/8,
floored at zero. Both require 26 weeks of history and nine recent complete
weekly values. Both use identical eligible cases. No seasonal tweak is justified yet.

MAE is mean absolute patient-count error. MASE divides each error by the mean
absolute adjacent-week change in its available training history, then averages.
Zero scales are omitted from MASE only and counted. No epsilon substitutions.
Direction compares shrink/unchanged/grow signs. Persistence predicts unchanged;
its grow/shrink-only abstentions count as incorrect, reported separately.

Every scored prediction has an empirical 80% band: symmetric absolute residual
quantile from at most 52 within-trust historical errors (minimum 8), with all
calibration targets published by issue. History gaps are not bridged. Coverage
and mean width are reported; serial dependence prevents a coverage guarantee.
Metrics average paired forecast cases, not equally weighted trust-level means.
The row-level parquet enables auditing; JSON includes skipped-case counts.

Later: quantiles alone do not identify growth probability. Aggregate backlogs
cannot identify diagnosis/treatment capacities or long-wait age profiles.
Scenario calibration must not be presented as causal validation.
