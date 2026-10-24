# Forecast methodology (updated through Stage 5)

**Approximate: latest revised values.** Release dates are M+2/day14; source
upload dates are separate. Available-at filtering does not remove revision
leakage. The 130-trust acute/specialist cohort and merger mapping describe the
current organisation footprint retrospectively, not historical deployment units.

## Merger and cohort handling

`pipeline.mergers` preserves raw tables and sums predecessor/successor counts
before each documented weekly/monthly boundary. Rates are rebuilt from counts.
Post-merger predecessor observations, including zeros, are removed. An entirely
missing provider-period or an explicitly suppressed count is not treated as zero.
A missing cancer/test category contributes zero only when the provider's broader
report for that metric/period exists. Provenance keeps component codes and the
latest contributing release date.

The core requires observed evaluation-era backlog and positive 31D cancer
activity in the latest 12 months, among live NHS acute/specialist providers.
Community-only, mental-health and independent providers are excluded. Retired
providers map to successors; RET/RP6 are retained specialist cancer providers.
The registry and `provider_scope.csv` give per-code evidence/decisions.

## Pairing and training

Headline targets are exactly 4/8/12 weeks **after issue**. Stage 2 cases were
regenerated on merged counts: **4,371 / 4,113 / 3,855** at these horizons across
35 scheduled origins. Every model uses identical eligible cases. April 2023
history supports lags; scored outcomes are never before October 2023.

Weekly training snapshots use features released by their historical issue; labels
must be released by the current fit. Calendar lags retain missing weeks.
Warm-up training permits 9–25 observed weeks in a 26-week window; evaluation
requires the baseline 26-week history rule. Trust code is not a categorical feature.

Compare persistence, eight-week drift, partial reversion towards the trust's
26-week mean (global horizon weight refitted from published labels), reversion
with annual/Christmas/national trend context, and LightGBM 10/50/90th quantiles of
`log1p(target)-log1p(latest)`. LightGBM uses 100 rounds, 15 leaves, learning rate
0.04, minimum leaf 100, two threads. Features include backlog levels/lags,
first-attendance volume proxy, CWT performance, DM01, publication age, calendar,
national trend and past strikes. Missing monthly features remain NaN.

## Calibration, selection and review

Intervals use earlier issued errors with published outcomes; <200 errors borrows
baseline widths. Nominal 80% coverage is empirical, not guaranteed. Classifier
Platt calibration also uses earlier published outcomes; it did not improve Brier.
Research outputs retain raw/calibrated Brier scores and reliability curves.
Display is only 4-week likely up/down/unclear, with assumed 0.6/0.4 thresholds and
agreement with count direction. No probabilities or longer-horizon signals.

The count gate requires beating both baselines on MAE and MASE at +8 and +12;
lowest combined 8/12 MASE wins among passing candidates. An expanding
published-history mean-error correction was tested and rejected. The selected
**50:50 LightGBM/last-value blend was chosen post-hoc on the back-test**.
Its fixed weight and blended interval endpoints do not constitute independent
validation or formal quantile calibration.

Trust-cluster bootstrap: 10,000 whole-trust resamples, seed 42, percentile 95%
intervals for gain in paired summed absolute errors. Preserves within-trust
dependence, but not common shocks or selection uncertainty. Large swings are
`abs(actual-last)>0.30*last`, an outcome-defined post-hoc slice.

Paired-sum MAE sums actual/predicted counts over exactly the scored trusts at each
issue before averaging absolute errors. Coverage varies; this is not official
England. National forecasts and summed trust bands remain withheld.
Stage 4 reference JSON/parquet retain old results; merger comparison also reports
exact common cases on unchanged footprints. Overall before/after differences
include changed trust units/cohorts. See README for current results.
