# Cancer Clock

Hospital-level forecasts of NHS patients still waiting beyond 62 days.
Stage 3 adds interpretable reversion, LightGBM and a separate growth classifier.
No personal waiting-time predictions, simulator or web app yet.

## Run locally

Python 3.11+ required. First-time setup only: `python3.12 -m venv .venv`.
On Mac, LightGBM needs OpenMP: install it once with `brew install libomp`.
Then, from the `cancer-clock` folder:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q -W error
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.check
```

Expected: **38 tests pass**, then both snapshot checks pass. All data/results are
bundled. No keys or downloads are needed for these checks. Windows uses
`.venv\Scripts\python.exe` in place of `.venv/bin/python`.

Reproduce model fitting and evaluation (about four minutes in our environment):

```sh
.venv/bin/python -m models.forecast
```

Earlier baseline stage still runs with `python -m models.backtest`.
Optional raw-data rebuild: `python -m pipeline.build --end 2026-08`.
Cached sources support `pipeline.build --offline --end 2026-08`.

## Measured result: true future forecasts

Exact same issue-anchored cases as Stage 2; MAE is patients per forecast.

| Model | +4 weeks | +8 weeks | +12 weeks |
| --- | ---: | ---: | ---: |
| Last value | 29.98 | 32.00 | 33.91 |
| Recent trend | 52.65 | 61.12 | 72.37 |
| Partial mean reversion | 29.37 | 31.63 | 33.18 |
| Reversion + season + national trend | 28.97 | 32.07 | 34.83 |
| LightGBM | **28.08** | **31.15** | **32.22** |

LightGBM also beats both baselines on MASE at 8/12 weeks: the exploratory count
forecast gate passes. MAE gains over last-value are **6.3%, 2.7%, 5.0%**.
Its nominal 80% intervals cover **84.9%, 84.5%, 83.2%** of observed outcomes.
These modest retrospective gains are not independent validation or significance.

The growth classifier is experimental. Calibrated Brier scores are
**0.2493 / 0.2591 / 0.2563**, versus **0.25** for constant 50% probability.
Platt calibration did not improve Brier over the raw model at any horizon.
Do not claim reliable growth probabilities, particularly at 8/12 weeks.

## Data and limits

133 core NHS trusts; all have coordinates. 178 weekly observations from April
2023 support lags; monthly comparable data/evaluation outcomes start October
2023. All models use the shared core list; RVY and independent providers stay out.
Latest forecast issue: **18 October 2026**, the first Sunday after the snapshot's
last assumed release. 129 trusts have sufficient recent history; four have
explicit unavailable statuses. This is not a live feed.

**Approximate: latest revised values.** Every dataset assumes publication on
14th of observation month + 2. Features AND training/calibration outcomes must
be released by issue. Original historical vintages remain unverified.

Results: `outputs/backtest_model.json`, `backtest_classifier.json`, row-level
prediction/feature parquets, and `forecasts_latest.json`. Reliability plot:
`docs/fig_growth_calibration.png`. Details: `docs/stage_3.md`, `methodology.md`.

## Upload / attribution

Use **[GitHub web upload instructions](docs/web_upload.md)**. Upload a fresh ZIP
extraction; testing recreates caches. Uploading does not delete old cache folders.
Code: MIT. NHS data: OGL v3.0, source URLs/hashes in `docs/source_manifest.csv`.
Locations: NHS sources and postcodes.io. Strike sources: `data/static/strike_dates.csv`.
HRT remains primary. Gemini, Tiger Data and Vultr are planned integrations;
ElevenLabs/Delta remain optional later scope.
