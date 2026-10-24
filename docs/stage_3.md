# Stage 3 handoff

Historical Stage 3 handoff. Stage 4's review, blend, display restrictions and
current test count supersede this page; see `stage_4.md` and the README.

**Done:** all 38 tests pass with warnings treated as errors; pipeline/model snapshot
checks pass. Full fit took 234 seconds on this Linux runtime, without warnings.
Mac warnings were not reproduced; see warnings.md. No blanket suppression added.

## Results

All five models use identical **issue-anchored** Stage 2 cases:
4,446 / 4,182 / 3,919 at +4/+8/+12 weeks. Full MAE comparison is in README.
LightGBM MAE: **28.08 / 31.15 / 32.22**, improving on last-value by
**6.3% / 2.7% / 5.0%**. MASE: **2.805 / 2.956 / 3.083** versus baseline
**2.981 / 3.063 / 3.271**. Nominal 80% coverage: **84.9% / 84.5% / 83.2%**.

Both LightGBM and plain reversion pass the 8/12-week count gate; LightGBM is selected.
The context-reversion model fails that gate. No settings were retuned on these scores.
Gains are modest and exploratory; archived original data and independent validation
are still missing. Keep `approximate: latest revised values` beside headline results.

Growth classifier Brier (lower is better):

| Issue horizon | Raw classifier | Platt calibrated | Historical frequency | Constant 50% |
| --- | ---: | ---: | ---: | ---: |
| 4 weeks | 0.2354 | 0.2493 | 0.2573 | 0.2500 |
| 8 weeks | 0.2530 | 0.2591 | 0.2580 | 0.2500 |
| 12 weeks | 0.2526 | 0.2563 | 0.2578 | 0.2500 |

Raw binary accuracy: **61.8% / 59.1% / 59.6%**. Ties count as non-growth;
grow/shrink-only accuracy is also reported. Platt did not improve Brier. The
reliability plot includes sparse extreme bins (counts are in JSON). Do not pitch
these as validated growth probabilities.

Latest source-supported issue: **18 October 2026**. 129/133 trusts have forecasts;
RAP, RVJ, RWF and RY2 lack sufficient recent observed history and are explicitly
unavailable. All 133 stay in the core list/map. No values or code mergers invented.

## Run and upload

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.check
.venv/bin/python -m models.forecast
```

Mac OpenMP prerequisite: `brew install libomp`. Final command retrains; previous
checks use the bundled results. Expected `38 passed`, two snapshot success messages,
then the comparison table and `GO_EXPLORATORY | selected: lightgbm`.

Use **web_upload.md** after successful local checks. Upload a clean extraction,
not the tested working folder. Commit summary:
`Test mean reversion and machine learning against the backlog baseline`

## Files changed

Added:
- `models/features.py`, `learners.py`, `calibration.py`, `forecast.py`, `check.py`
- `tests/test_models.py`, `data/static/strike_dates.csv`
- `outputs/backtest_model.json`, `backtest_model_predictions.parquet`,
  `backtest_classifier.json`, `model_features.parquet`, `forecasts_latest.json`
- `docs/fig_growth_calibration.png`, `stage_3.md`, `warnings.md`, `web_upload.md`

Modified: README, config, requirements, models/__init__, packager, assumptions, methodology,
git_workflow, historical stage_2 handoff. Earlier source datasets and baseline
predictions are unchanged.

Delete on GitHub: `__pycache__/`, `pipeline/__pycache__/`, `tests/__pycache__/`,
`.pytest_cache/`, plus any other generated `__pycache__/` directory. No source
files need deletion. The ZIP excludes these caches at every depth.
