# Stage 5 handoff

Completed merger correction, rerun of Stages 2/3/review/4, and the daily simulator.
68 tests pass with warnings as errors; pipeline, model, bottleneck and simulation
snapshot checks pass. No new dependencies. Rounak's clinical review is pending.

## Merger audit and forecast changes

| Predecessor → successor | First merged backlog week | Last pre-merger counts → first merged count |
| --- | --- | --- |
| RVJ → RA7 | 2026-07-05 | 201 + 222 = 423 → 388 |
| RAP → RAL | 2025-01-05 | 298 + 126 = 424 → 444 |
| RY2 → RWW | 2026-04-05 | 25 + 9 = 34 → 36 |
| RVY → RBN | 2023-07-09 | 176 + 85 = 261 → 239 |

RVY's legal/monthly merger is 1 July 2023; its weekly reporting still contains
RVY on 2 July, so weekly stitching starts 9 July. Registry evidence distinguishes
legal/monthly and weekly boundaries. RET is Walton Centre, not RDE; RET and RP6
still report cancer treatment. Their zero backlogs are not retirement evidence.

The automated detector ranks cessation plus concurrent jumps (with location and
continued-CWT checks); it suggests all four verified mappings, but never applies
a suggestion without the registry. Raw tables are preserved. Counts, including
historical community activity absorbed into an acute successor, are summed before
the boundary; missing components propagate and rates are recomputed. Only current
acute/specialist cancer providers enter the 130-trust core/map. Retired location
rows remain for audit with `merged into X` notes and `in_core_universe=False`.

Full before/after trust MAE, paired-sum MAE and large-swings comparisons are in
README and `backtest_model.json → review → merger_impact`, including identical
cases for unchanged trusts. Frozen Stage 4 references in `data/static/` make the
comparison reproducible. Overall cohort changes prevent a causal attribution.
The 50:50 blend is explicitly **selected post-hoc on the back-test**.

| Latest issue 18 Oct 2026, blend point | +4 weeks, before → after | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| RA7 | 363.2 → 415.3 | 360.9 → 422.7 | 352.2 → 425.0 |
| RAL | 137.5 → 136.1 | 143.7 → 143.4 | 145.9 → 144.7 |

## Driver and simulator changes

Diagnosis uses cancer-specific FDS; treatment uses 31D modalities. DM01 is context
only. RTH becomes treatment-limited (radiotherapy 61.7% vs England 88.7%); R0A is
diagnosis-limited, with qualifying lower GI 59.2% vs 67.4%, n=1,926. All mixed trusts
show both drivers. [Ten live examples](bottleneck_examples.md) await clinical review.

124 simulator fits, 122 within the declared in-sample error threshold; median
RMSE 6.73 patients. [Fit distribution and assumptions](simulator_method.md) explain
the six unavailable trusts, two poor fits and 29 prior conflicts. Each bundled
RTH/RA7/RAL comparison has six plans × 256 runs. Ages stay in days across diagnosis
and treatment. Recovery accounts for delayed excess after a surge.

For RTH at day 182, baseline median backlog is 169; a five-day strike gives 171,
strike plus 10% diagnosis 171, strike plus 10% treatment 88. This conditional result
is consistent with its treatment signal, not proof of causal benefit. RAL's fitted
treatment constraint conflicts with its diagnosis label, illustrating weak
identification. Monte Carlo bands omit structural/parameter uncertainty.

## Reproduce and upload

The README checks use bundled data. To regenerate affected stages in order:

```sh
.venv/bin/python -m pipeline.mergers
.venv/bin/python -m models.backtest
.venv/bin/python -m models.forecast
.venv/bin/python -m analysis.bottleneck
.venv/bin/python -m sim.calibrate
.venv/bin/python -m sim.scenarios
```

`models.forecast` also regenerates the review. Optional source rebuild first:
`python -m pipeline.build --end 2026-08`, then `python -m analysis.build_diagnostics`.
Raw downloads are excluded from the ZIP and may need fetching. For editable
experiments, `sim.scenarios --help` exposes trust, run count, horizon, start week,
strike days, winter/surge duration and size, and extra capacity. Results are JSON.

Use [web upload](web_upload.md), from a fresh extraction after local checks.
Delete old `analysis/.gitkeep` and `sim/.gitkeep` if present, plus generated cache
directories at every depth. The complete ZIP has 100 files, each below 25 MB, and
excludes caches, raw downloads, virtual environments and secrets.
