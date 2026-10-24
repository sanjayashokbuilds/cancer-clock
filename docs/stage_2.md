# Stage 2 handoff (historical)

Stage 3 adds models; current run/upload instructions are in README and web_upload.md.

Done: 29 tests pass; seven snapshot checks pass. 133 core trusts, all geocoded;
178 backlog weeks from 9 April 2023. Monthly datasets still start October 2023.
Every dataset uses M+2/day14 and carries `approximate: latest revised values`.
RVY has 13 earlier observations, none from October 2023, so is excluded from core/map.
Source upload dates are retained separately. Historical vintages remain unverified.

35 rolling origins (7 Jan 2024–16 Aug 2026), 52,294 scored baseline predictions.
Each has an empirical 80% band. Both baselines use identical eligible cases;
missing history/outcomes and insufficient calibration are counted in the JSON.

| Horizon from issue | Cases per baseline | Last-value MAE | Drift MAE | Last-value MASE | Drift MASE | Last-value 80% coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 weeks | 4,446 | 29.98 | 52.65 | 2.981 | 5.264 | 81.0% |
| 8 weeks | 4,182 | 32.00 | 61.12 | 3.063 | 5.977 | 80.2% |
| 12 weeks | 3,919 | 33.91 | 72.37 | 3.271 | 7.070 | 79.7% |

Last-value wins at every tested horizon. No ML model has been trained.
Observation-anchored scores also appear in the report, with actual issue leads:
4 weeks -> −7 to −3; 8 -> −3 to +1; 12 -> +1 to +5. Do not pitch negative leads
as future forecasts. Direction metrics distinguish unchanged predictions explicitly.

## Run

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.backtest
```

Expected: `29 passed`, snapshot checks passed, a 12-row baseline table and
`Stage 2 backtest complete. No ML model has been trained.` No raw downloads needed.

Commit after these checks:

```sh
git add .
git diff --cached --stat
git commit -m "Fix release timing and test simple backlog forecasts against NHS history" -m "Revised files were making older observations look unavailable, so release timing now follows the same first-release assumption across datasets. Added the core NHS trust list, filled the map gaps and kept April backlog history for training. The backtest compares last-value and recent-trend forecasts using only data available at each issue date, with the revised-value limitation shown. Last-value forecasts performed better, giving us a benchmark for the next model."
git push -u origin main
```

## Files changed

Added: `pipeline/universe.py`; `models/{__init__,baselines,backtest}.py`;
`tests/test_backtest.py`; `data/static/{core_trusts,location_overrides}.csv`;
`outputs/backtest_baselines.json`; `outputs/backtest_baseline_predictions.parquet`;
this handoff.

Modified: `config.py`, `README.md`, pipeline build/check/common/fetch/locations/
parse_backlog/parse_cwt/quality, `scripts/package_repo.py`; all seven processed
parquets; trust locations; quality report; source manifest; Oxford chart;
assumptions, methodology and data dictionary. Stage 1 handoff is marked historical.
Deleted: none. Requirements unchanged.
