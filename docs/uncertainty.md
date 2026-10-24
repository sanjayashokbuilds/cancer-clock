# Capacity uncertainty and dose response

The new decision view uses **256 paired draws** for each of the 124 calibrated
trusts. The other six retain explicit unavailable reasons. Existing Stage 5 point
fits and source tables are unchanged. Output: `outputs/decision_support.json`.

## What the ranges include

At each trust's published 13-week calibration window, compute finite-difference
sensitivities of total backlog to both capacity ratios. Resample centred residuals
in circular blocks of three observed weekly residuals. Use the joint SVD update
so the two capacities can vary together, keeping their original 0.4–1.8 bounds.
The imposed initial observation is excluded from residual fitting.

A direction whose local standard uncertainty spans half the permitted range is
weakly identified. Sample that direction uniformly within the bounds rather than
assigning zero variance. Replay candidates through the nonlinear queues and retain
only those with calibration SSE no greater than the original SSE plus
`6 × residual variance × 3`. The one-patient-squared variance floor, block length,
weak-direction bounds and fit budget are explicit sensitivity assumptions, not
estimated confidence levels. Metadata exposes all of them and acceptance counts.

Each accepted pair is replayed from the original calibration initial age mix to
obtain its own end state, then across the publication gap. Capacity is held fixed
within a draw and shared across every plan. Arrivals and service noise are also
paired, so differences compare the same simulated conditions.

These are **process + capacity-parameter sensitivity ranges**, not validated
predictive intervals or full structural uncertainty. Conversion, age shape, stage
split, service order, uniform weekends and the strike multiplier remain assumed.
A good fit does not identify the cause of a backlog. Prior conflicts and poor fits
remain visible.

## Main decision view

The dose grid is 0, 1, 2, 3, 4, 5, 10, 15 and 20 percent extra capacity in either
stage, starting day 28, with a five-day strike at the same point. Each point gives
the day-182 backlog median and 10–90% range. The local benefit is calculated within
each draw as `(backlog at 0% − backlog at 5%) / 5`, then summarised: fewer patients
per **one percentage point** of extra capacity. Negative or negligible effects are
retained. This is not a staffing/cost conversion or causal recommendation.

Six full comparisons are precomputed: baseline, strike, strike +10% diagnosis,
strike +10% treatment, six-week −10% winter capacity and four-week +20% referrals.
They include trajectories, peaks, recovery, >104-day changes and assumptions.
Recovery accounts for delayed excess after the temporary shock, with the existing
14-day persistence rule and horizon censoring.

Treatment labels follow qualifying 31D evidence: Oxford shows **Radiotherapy
capacity (stage proxy)**. The simulated change still affects the whole treatment
stage; the data cannot isolate radiotherapy's marginal capacity effect. Royal Free
retains a visible prior conflict rather than a modality label unsupported by 31D.

## How much bands widen

Widths below compare identical process draws at day 182 for strike +10% treatment.

| Trust | Process-only width | With capacity uncertainty | Width ratio |
| --- | ---: | ---: | ---: |
| RTH | 20.01 patients | 45.78 patients | 2.29× |
| RAL | 16.34 patients | 38.52 patients | 2.36× |
| RA7 | 263.92 patients | 447.08 patients | 1.69× |

The JSON also reports all six scenario comparisons per trust, absolute width
changes and a cohort summary. Zero process width gives a null ratio with a reason;
the median width ratio is **2.91× across 120 valid ratios**. Four have effectively
zero process-only width; one trust's interval narrows slightly. We do not force
every interval to widen. Oxford's process-only reference curve is
retained separately to reproduce the independent 0/2/5/10/20% treatment check.

Rebuild: `python -m sim.decisions --workers 4`. Check without recomputing:
`python -m sim.decisions --check`. No future or unpublished outcomes enter this fit.
