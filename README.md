# Cancer Clock

Hospital-level planning prototype for NHS cancer backlogs: patients still
waiting beyond 62 days. Stage 2 supplies real-data baselines; no ML, simulator,
API or web app yet. This is not a personal waiting-time predictor.

## Run on Mac / Linux

Python 3.11+ required. From the `cancer-clock` folder, first-time setup:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

With an existing environment, skip creation and run:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pipeline.check
.venv/bin/python -m models.backtest
```

Windows: use `py -3.12 -m venv .venv`, then `.venv\Scripts\python.exe`.
The bundled data and baseline evaluation run offline, without API keys.
Open `docs/fig_rth_backlog.png` to inspect Oxford's historical observations.

## What is included

- CWT and DM01: October 2023–August 2026, 35 monthly observations.
- Backlog: 178 weeks, 9 April 2023–30 August 2026. April–September can train;
  scored outcomes start no earlier than October 2023.
- `data/static/core_trusts.csv`: 133 NHS trusts with observed backlog in the
  evaluation era. All have coordinates; RVY and independent providers are excluded.
- `outputs/backtest_baselines.json`: baseline scores and methodology.
- `outputs/backtest_baseline_predictions.parquet`: every scored prediction,
  actual, uncertainty band, issue/observation/target date and training scale.

## Interpretation

**Approximate: latest revised values.** Every dataset assumes first release on
14th of observation month + 2. Source upload dates are retained separately.
Historical vintages are unverified: later revisions may still affect results.

Both baseline models run on identical cases. The last-value baseline predicts
no change; drift extends the previous eight-week trend. Bands use only errors
whose outcomes were available by the issue date. Coverage is measured honestly.

The report separates horizons from the **last observation** and from the
**issue date**. With seven-week-old data, +8 weeks from observation is only +1
week from issue. Negative/zero issue leads are retrospective estimates/nowcasts,
not future forecasts. Use issue-based results for planning comparisons.

## Rebuild from NHS sources (optional)

```sh
.venv/bin/python -m pipeline.build --end 2026-08
.venv/bin/python -m models.backtest
```

Cached raw files allow `pipeline.build --offline --end 2026-08`.
Raw files are excluded from this ZIP and Git. No filling of missing counts,
no invented locations, no inferred merger crosswalks.

See `docs/stage_2.md` for results/changes and `docs/methodology.md` for metrics.
Code: MIT. NHS England data: Open Government Licence v3.0, with source URLs and
hashes in `docs/source_manifest.csv`. Postcode coordinates: postcodes.io.
HRT is the primary track; Gemini, Tiger Data and Vultr integrations are planned,
not implemented. Optional ElevenLabs/Delta work remains later scope.
