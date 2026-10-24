# Stage 4 handoff

Built the requested Stage 3 review changes and bottleneck screening. No Stage 5
simulation has been added. All 52 tests pass with warnings treated as errors;
pipeline, model/review and bottleneck snapshot checks pass.

## Results

Original LightGBM trust-bootstrap 95% gain intervals: 3.8–8.8%, −0.7–5.8%,
0.8–8.8% at issue +4/+8/+12. The 8-week interval includes zero. Original-model
large-swings gains: 13.6%, 11.4%, 15.3%; this is a post-hoc outcome-defined slice.

The published-history mean correction worsened results. The fixed 50:50 blend
is selected: trust MAE 28.09 / 30.44 / 31.73; signed error +2.68 / +0.13 / −2.55.
Paired-sum MAE beats naive by 14.6% / 5.5% / 6.1%. National forecasts remain
withheld because full England coverage and aggregate intervals are unvalidated.
Only qualitative 4-week growth signals are exported.

All 133 core trusts have June–August 2026 bottleneck labels: 54 diagnosis-limited,
4 treatment-limited, 16 mixed, 59 no clear bottleneck. There are 128 trusts with
both sides screened, two partial and three insufficient. Missing evidence is
flagged; confidence is heuristic evidence strength, not causal certainty.
[Ten examples for Rounak](bottleneck_examples.md) are ready for clinical review.

## Run and upload

Follow [exact Mac update/test/push commands](git_workflow.md).
Quick checks from the repository:

```sh
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.check
.venv/bin/python -m analysis.bottleneck --check
```

Rebuild only the new work: `python -m models.review`, then
`python -m analysis.bottleneck`. Full historical refitting remains
`python -m models.forecast`. Earlier source data, core list and original
row-level Stage 3/baseline predictions are preserved.

Commit: `Add bottleneck checks and temper the longer-range backlog forecasts`

## Files changed

Added: `models/review.py`; `analysis/__init__.py`, `build_diagnostics.py`,
`bottleneck.py`; `tests/test_review.py`, `test_bottleneck.py`;
`data/processed/dm01_bottleneck_reference.parquet`;
`outputs/backtest_adjusted_predictions.parquet`, `bottlenecks.json`;
`docs/bottleneck_method.md`, `bottleneck_examples.md`, `stage_4.md`.

Modified: README, config, model forecast/check modules, DM01 parser (optional
English scope), model/pipeline tests, three model JSON reports, packager,
methodology/assumptions and upload documentation. Dependencies are unchanged.

Delete on GitHub: **no source files**. Remove any tracked `__pycache__/` (including
under pipeline, models, analysis and tests) and `.pytest_cache/`; terminal
commands handle this. The complete ZIP excludes caches, raw downloads, virtual
environments, secrets and Git internals, and stays within web-upload limits.
