# Stage 3 methodology

**Approximate: latest revised values.** Release dates are M+2/day14; source
upload dates are retained separately. Archived original values are unavailable.
Release-aware code does not eliminate revision leakage in the source snapshot.

## Pairing and training

Target: trust count still waiting beyond 62 days. Stage 3 headlines use targets
exactly 4/8/12 weeks **after issue**, not after the old observation. The saved
Stage 2 issue cases are immutable: 4,446 / 4,182 / 3,919 per model, across 35
origins in 2024–2026 and 133 core trusts. Missing cases cannot silently disappear.

Training uses weekly historical issue snapshots. Each feature is calculated
from data released at that historical issue; each label must itself be released
by the current fit date. Calendar lags preserve missing weeks; rolling means use observed values with counts. April history may
train; scored outcomes are never before October 2023. Warm-up training can use
9–25 observed weeks within the 26-week window; scored cases retain Stage 2's
26-week history rule. Trust codes are not merged or used as categorical predictors.

## Candidates

- Persistence and eight-week endpoint drift retain the Stage 2 scores/bands.
- Partial reversion: `latest + weight × (rolling 26-week mean − latest)`.
  One global weight per horizon, bounded [0,1], refitted using published labels.
- Context version adds annual sine/cosine changes, Christmas and national
  eight-week trend. Coefficients are bounded/regularised, not causal effects.
- LightGBM: global 10th/50th/90th quantiles of `log1p(target) − log1p(latest)`.
  Inverse transformation handles zeros; crossing quantiles are sorted.
  Fixed 100 rounds, 15 leaves, 0.04 learning rate, minimum leaf 100, two CPU threads.
  Training-only count weights/caps reduce relative-error emphasis. No reported
  test score was used to tune these settings.

Features: backlog lags/changes, rolling means/variation, first-attendance volume
proxy and backlog normalisation, FDS/62D/31D-modality performance, seven DM01
list sizes/waits/activity, publication ages, annual/Christmas/Easter calendar,
national backlog trend and past strike-day indicators. Future strikes are never
read. Missing monthly features remain NaN; first attendances are not referrals.

## Uncertainty and classification

Reversion intervals use earlier issued out-of-sample absolute errors divided by
`1 + latest`. LightGBM bands expand using earlier issued quantile errors. Only
published calibration targets qualify; fewer than 200 errors uses baseline
widths as explicit warm-up. Nominal coverage is 80%, measured rather than guaranteed.

The separate binary classifier predicts `target > latest`. Ties are **non-growth**;
grow/shrink-only accuracy additionally excludes ties. Report raw and Platt-calibrated
probabilities, Brier scores, 10-bin reliability curves/counts, frequency, coin and
hard non-growth benchmarks. Platt fitting uses earlier issued predictions with
published labels. This run's calibration does not improve Brier: probabilities
remain experimental. No growth probability is inferred from three quantiles.

MAE and MASE average paired forecast cases. MASE's scale uses available adjacent
weekly changes; zero scales are excluded from MASE only and counted. Direction
includes unchanged. Overlapping dates and trusts are dependent; no significance claim.

Count gate: beat **both** baselines on MAE and MASE at issue +8 AND +12 weeks.
Among passing candidates select lowest combined 8/12 MASE; otherwise use persistence.
Selection on this comparison is exploratory, not independent future validation.
