# Forecast-based recovery plans

The planning horizon is 84 days after the forecast issue date. The existing
post-hoc 50:50 blend supplies the level, linearly interpolated from the latest
reported count through its issue +4/+8/+12-week points. Interpolated weeks are
display values, not additional fitted forecasts. No forecast model is retrained.

For each paired draw and week, let F be the central forecast, S0 the unchanged
queue simulation, Ss the same simulation with selected pressures, and Sp the
simulation with those pressures and extra capacity:

- Pressure change = Ss − S0.
- Capacity change = Sp − Ss.
- Displayed plan = max(0, F + Sp − S0).
- Displayed no-extra-capacity comparison = max(0, F + Ss − S0).

The signed differences are added. Equivalently, a positive capacity benefit
Ss − Sp is subtracted. Capacity draws, starting states, arrival uniforms and
daily service noise are shared across each comparison. Quantiles are taken
after subtracting paired paths and flooring displayed counts, never by
subtracting marginal quantiles. The 0–5% benefit is the paired difference in
displayed day-84 counts divided by five, including the floor at zero.

The shaded plan range is the 10th–90th percentile of this change sensitivity
around a fixed central forecast. It excludes the forecast's own uncertainty;
the original forecast band is retained separately. Queue structure, age mix,
conversion and service-order uncertainty are not quantified. These results
are conditional planning comparisons, not measured causal staffing effects.

## Availability

The simulator must have published inputs, a converged fit, normalised history
RMSE ≤0.30 and both capacity directions identified under the existing sensitivity
check. Prior conflicts remain visible but do not themselves block a plan.
Absolute simulator/forecast level disagreement no longer blocks a plan.
A complete matching forecast is still necessary; missing forecasts are not filled.

The machine-readable before/after counts, all excluded hospitals and the Oxford
check are in `outputs/recovery_plan_review.json`. Original six-month outputs in
`outputs/decision_support.json` remain unchanged and appear only in details.

Before: 66 plans available, 57 blocked by absolute level mismatch, one missing
forecast and six missing simulation inputs. After: 109 available; 20 simulator
exclusions plus RWF's missing forecast. Fifty-three previously blocked plans
are released, while ten previously visible plans now fail the simulator checks.

Oxford with a strike and +10% treatment capacity: 176.315 → 148.384 at day 84;
conditional plan range 147.859–148.992, paired capacity benefit 27.948 and
near-zero marginal benefit 2.825 people per extra percentage point.

The optional forecast-weighted capacity refit was not performed. Matching the
forecast level by construction is not evidence of a better calibrated simulator.

## Reproduce

`python -m sim.planning_grid --workers 6` regenerates all paired 12-week grids.
`python -m sim.planning_grid --check` verifies the complete snapshot.
`python -m pytest -q -W error` checks the model and API contracts.
`python -m scripts.review_recovery_plans` reproduces the availability/result report.

Validation: 138 tests passed with warnings as errors; frontend production build
passed. An independent replay using the original daily simulator reproduced
Oxford's paired result. Browser checks at 1440×900 covered the new result,
assumptions drawer, exact hold-back wording and Oxford fallback.
